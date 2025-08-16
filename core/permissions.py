"""权限管理模块 - 统一权限检查和装饰器

提供简洁的权限验证机制，支持装饰器模式
"""
import time
import threading
from enum import Enum
from functools import wraps
from typing import Dict, Optional
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger


class PermissionLevel(Enum):
    """权限级别枚举"""
    SUPER_ADMIN = "super_admin"  # AstrBot系统管理员
    GROUP_ADMIN = "group_admin"  # 群聊管理员
    USER = "user"  # 普通用户


class PermissionManager:
    """权限管理器 - 处理权限验证和缓存"""
    
    def __init__(self):
        # 群管理员信息缓存
        self._group_admin_cache: Dict[str, bool] = {}
        # 缓存时间戳
        self._cache_timestamps: Dict[str, float] = {}
        # 缓存有效期（5分钟）
        self._cache_ttl = 300
        # 缓存锁，确保线程安全
        self._cache_lock = threading.RLock()

    def get_user_permission_level(self, event: AstrMessageEvent) -> PermissionLevel:
        """获取用户权限级别"""
        # 检查是否为AstrBot系统管理员
        if event.role == "admin":
            return PermissionLevel.SUPER_ADMIN

        # 检查是否为群聊管理员
        group_id = event.get_group_id()
        if group_id and self._is_group_admin(event, group_id):
            return PermissionLevel.GROUP_ADMIN

        return PermissionLevel.USER

    async def _is_group_admin_async(self, event: AstrMessageEvent, group_id: str) -> bool:
        """异步检查是否为群聊管理员（优先使用API）"""
        try:
            user_id = event.get_sender_id()
            if not user_id:
                return False

            # 使用锁保护缓存操作
            with self._cache_lock:
                # 检查缓存
                cache_key = f"{group_id}_{user_id}"
                current_time = time.time()

                if (
                    cache_key in self._group_admin_cache
                    and cache_key in self._cache_timestamps
                    and current_time - self._cache_timestamps[cache_key] < self._cache_ttl
                ):
                    return self._group_admin_cache[cache_key]

                is_admin = False
                
                # 优先使用aiocqhttp协议API获取真实权限
                platform_name = event.get_platform_name() if hasattr(event, 'get_platform_name') else None
                logger.debug(f"检测到平台类型: {platform_name}")
                
                if platform_name == "aiocqhttp":
                    try:
                        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                        if isinstance(event, AiocqhttpMessageEvent) and hasattr(event, 'bot'):
                            client = event.bot
                            logger.debug(f"获取到 aiocqhttp 客户端: {type(client)}")
                            
                            if client and hasattr(client, 'api'):
                                logger.debug(f"开始调用 get_group_member_info API - 群:{group_id}, 用户:{user_id}")
                                
                                member_info = await client.api.call_action('get_group_member_info', 
                                                                          group_id=int(group_id), 
                                                                          user_id=int(user_id))
                                
                                logger.debug(f"API 返回结果: {member_info}")
                                
                                if member_info:
                                    # 处理不同的响应格式
                                    data = member_info
                                    if 'data' in member_info:
                                        data = member_info['data']
                                    
                                    role = data.get('role', 'member')
                                    is_admin = role in ['owner', 'admin']
                                    
                                    logger.info(f"用户 {user_id} 在群 {group_id} 的QQ角色: {role}, 管理员权限: {is_admin}")
                                    
                                    if is_admin:
                                        # API 检测成功，直接返回结果
                                        self._group_admin_cache[cache_key] = True
                                        self._cache_timestamps[cache_key] = current_time
                                        self._cleanup_expired_cache(current_time)
                                        return True
                                else:
                                    logger.warning(f"API 返回空结果 - 群:{group_id}, 用户:{user_id}")
                            else:
                                logger.warning(f"客户端或API不可用 - client: {client}")
                        else:
                            logger.warning(f"事件类型不匹配或缺少bot属性 - 类型: {type(event)}")
                    except Exception as e:
                        logger.error(f"aiocqhttp API检查权限失败 - 群:{group_id}, 用户:{user_id}, 错误: {e}")
                        import traceback
                        logger.debug(f"详细错误信息:\n{traceback.format_exc()}")
                
                # 如果API检查失败或非aiocqhttp平台，使用platform_meta作为备用方案
                logger.debug(f"使用 platform_meta 作为备用权限检测方案")
                is_admin = self._check_platform_meta_admin(event, user_id)

                # 缓存结果
                self._group_admin_cache[cache_key] = is_admin
                self._cache_timestamps[cache_key] = current_time
                self._cleanup_expired_cache(current_time)

                return is_admin

        except Exception as e:
            logger.error(f"检查群管理员权限失败: {e}")
            return False

    def _check_platform_meta_admin(self, event: AstrMessageEvent, user_id: str) -> bool:
        """从platform_meta检查管理员权限"""
        if not hasattr(event, "platform_meta") or not event.platform_meta:
            return False
            
        try:
            owner_id = getattr(event.platform_meta, 'owner_id', None)
            group_admins = getattr(event.platform_meta, 'group_admins', []) or []

            # 检查是否为群主或管理员
            if owner_id and str(user_id) == str(owner_id):
                return True
                
            if group_admins and str(user_id) in [str(admin_id) for admin_id in group_admins]:
                return True
                
        except Exception as e:
            logger.debug(f"platform_meta权限检查失败: {e}")
            
        return False

    def _is_group_admin(self, event: AstrMessageEvent, group_id: str) -> bool:
        """同步版本的群管理员检查（仅使用platform_meta）"""
        try:
            user_id = event.get_sender_id()
            if not user_id:
                return False

            # 只使用platform_meta进行同步检查
            return self._check_platform_meta_admin(event, user_id)

        except Exception as e:
            logger.error(f"同步权限检查失败: {e}")
            return False

    def _cleanup_expired_cache(self, current_time: float) -> None:
        """清理过期的缓存条目（在锁保护下调用）"""
        expired_keys = [
            key
            for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp >= self._cache_ttl
        ]

        for key in expired_keys:
            self._group_admin_cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")

    def check_permission(
        self, event: AstrMessageEvent, required_level: Optional[PermissionLevel] = None
    ) -> bool:
        """统一的权限检查方法
        
        Args:
            event: 消息事件
            required_level: 所需权限级别，None表示允许群管理员
            
        Returns:
            bool: 是否有权限
        """
        user_level = self.get_user_permission_level(event)

        if required_level == PermissionLevel.SUPER_ADMIN:
            # 仅允许系统管理员
            return user_level == PermissionLevel.SUPER_ADMIN
        else:
            # 允许系统管理员和群管理员
            return user_level in [PermissionLevel.SUPER_ADMIN, PermissionLevel.GROUP_ADMIN]

    async def check_admin_permission_async(self, event: AstrMessageEvent) -> bool:
        """异步检查是否有管理员权限"""
        # 检查是否为AstrBot系统管理员
        if event.role == "admin":
            return True

        # 检查是否为群聊管理员（使用异步API）
        group_id = event.get_group_id()
        if group_id:
            return await self._is_group_admin_async(event, group_id)
        
        return False

    def check_admin_permission(self, event: AstrMessageEvent) -> bool:
        """检查是否有管理员权限（兼容性方法）"""
        return self.check_permission(event)

    async def check_real_group_admin(self, event: AstrMessageEvent, group_id: str) -> bool:
        """检查真实的群管理员权限（使用aiocqhttp API）"""
        return await self._is_group_admin_async(event, group_id)

    def check_group_chat(self, event: AstrMessageEvent) -> bool:
        """检查是否为群聊"""
        return event.get_group_id() is not None


# 全局权限管理器实例
_permission_manager = PermissionManager()


# ==================== 装饰器函数 ====================

def admin_required(func):
    """管理员权限装饰器（使用异步权限检测）"""
    @wraps(func)
    async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
        # 使用异步权限检测，确保与status显示一致
        has_permission = await _permission_manager.check_admin_permission_async(event)
        if not has_permission:
            yield event.plain_result("此操作需要管理员权限（系统管理员或群管理员）")
            return
        
        async for result in func(self, event, *args, **kwargs):
            yield result
    
    return wrapper


def group_only(func):
    """群聊限制装饰器"""
    @wraps(func)
    async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
        if not _permission_manager.check_group_chat(event):
            yield event.plain_result("此功能仅支持群聊")
            return
        
        async for result in func(self, event, *args, **kwargs):
            yield result
    
    return wrapper


def super_admin_required(func):
    """系统管理员权限装饰器"""
    @wraps(func)
    async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
        if not _permission_manager.check_permission(event, PermissionLevel.SUPER_ADMIN):
            yield event.plain_result("此操作需要系统管理员权限")
            return
        
        async for result in func(self, event, *args, **kwargs):
            yield result
    
    return wrapper


# ==================== 便捷函数 ====================

def get_user_permission_level(event: AstrMessageEvent) -> PermissionLevel:
    """获取用户权限级别"""
    return _permission_manager.get_user_permission_level(event)


def check_permission(
    event: AstrMessageEvent, required_level: Optional[PermissionLevel] = None
) -> bool:
    """检查权限"""
    return _permission_manager.check_permission(event, required_level)


def check_admin_permission(event: AstrMessageEvent) -> bool:
    """检查管理员权限"""
    return _permission_manager.check_admin_permission(event)


def check_group_chat(event: AstrMessageEvent) -> bool:
    """检查是否为群聊"""
    return _permission_manager.check_group_chat(event)


async def check_real_group_admin_permission(event: AstrMessageEvent, group_id: str) -> bool:
    """检查真实的群管理员权限（使用aiocqhttp API）"""
    return await _permission_manager.check_real_group_admin(event, group_id)


async def check_admin_permission_async(event: AstrMessageEvent) -> bool:
    """异步检查管理员权限（推荐使用）"""
    return await _permission_manager.check_admin_permission_async(event)