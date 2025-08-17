"""通用工具模块 - 提供可复用的工具函数

包含消息构建、输入验证、通知管理等通用功能
"""
import time
from typing import Dict, List, Tuple
import astrbot.api.message_components as Comp
from astrbot.api import logger


class ValidationUtils:
    """输入验证工具类
    
    提供各种输入验证方法，确保数据安全和格式正确：
    - 参数数量验证
    - 文本长度验证 
    - 用户ID格式验证
    """
    
    @staticmethod
    def validate_params(params: list, min_count: int) -> bool:
        """验证参数数量是否满足最小要求
        
        Args:
            params: 参数列表
            min_count: 最小参数数量
            
        Returns:
            bool: 参数数量是否足够
        """
        return len(params) >= min_count

    @staticmethod
    def validate_input_length(
        text: str, max_length: int = 1000, field_name: str = "输入"
    ) -> Tuple[bool, str]:
        """验证输入长度，防止过长内容导致存储或显示问题
        
        检查流程：
        1. 验证文本不为空
        2. 检查长度是否超过限制
        3. 返回验证结果和错误信息
        
        Args:
            text: 要验证的文本
            max_length: 最大长度限制
            field_name: 字段名称，用于生成友好的错误提示
            
        Returns:
            tuple: (是否有效, 错误消息)
        """
        if not text or not text.strip():
            return False, f"{field_name}不能为空"

        if len(text) > max_length:
            return (
                False,
                f"{field_name}长度不能超过{max_length}个字符（当前{len(text)}个字符）",
            )

        return True, ""

    @staticmethod
    def validate_user_id(user_id: str) -> bool:
        """验证用户ID格式是否为纯数字
        
        QQ用户ID必须是数字格式，此方法确保输入符合要求
        
        Args:
            user_id: 用户ID字符串
            
        Returns:
            bool: 是否为有效的数字格式
        """
        return user_id.isdigit()


class MessageBuilder:
    """消息构建工具类
    
    负责构建各种类型的消息链，支持AstrBot的消息组件系统：
    - 欢迎消息链（支持占位符替换和@功能）
    - 黑名单通知消息链
    - 复合消息组件处理
    """
    
    @staticmethod
    def build_welcome_chain(welcome_msg: str, user_id: str, group_id: str) -> List:
        """构建欢迎消息链，支持占位符替换和@用户
        
        处理流程：
        1. 解析欢迎语模板中的{user}占位符
        2. 在{user}位置插入@组件
        3. 替换{group}占位符为实际群号
        4. 过滤空白组件，确保消息链有效
        
        支持的占位符：
        - {user}: 会被替换为@用户组件
        - {group}: 会被替换为群号
        
        Args:
            welcome_msg: 欢迎语模板，可包含占位符
            user_id: 用户ID，用于@功能
            group_id: 群组ID，用于占位符替换
            
        Returns:
            list: AstrBot消息链，包含Plain和At组件
        """
        chain = []
        
        # 解析欢迎语，替换占位符
        parts = welcome_msg.split("{user}")
        for i, part in enumerate(parts):
            if i > 0:  # 在{user}位置添加At组件
                chain.append(Comp.At(qq=user_id))
            # 替换{group}占位符并过滤空字符串
            if part:  # 只有非空部分才添加
                text = part.replace("{group}", group_id)
                if text.strip():  # 过滤空白文本，避免空Plain组件
                    chain.append(Comp.Plain(text))
        
        # 确保消息链不为空，提供默认欢迎消息
        if not chain:
            chain = [Comp.At(qq=user_id), Comp.Plain(" 欢迎加入群聊！")]
        
        return chain

    @staticmethod
    def build_blacklist_notification(
        user_id: str, is_success: bool, reason: str = "", error_msg: str = ""
    ) -> List:
        """构建黑名单通知消息链
        
        Args:
            user_id: 用户ID
            is_success: 操作是否成功
            reason: 黑名单原因
            error_msg: 错误消息
            
        Returns:
            list: 消息链
        """
        if is_success:
            chain = [
                Comp.Plain(f"🚫 检测到黑名单用户 {user_id} 加入群聊\n"),
                Comp.Plain(f"已自动踢出，原因：{reason}" if reason else "已自动踢出"),
            ]
        else:
            chain = [
                Comp.Plain(f"⚠️ 检测到黑名单用户 {user_id} 加入群聊\n"),
                Comp.Plain("自动踢出失败，请管理员手动处理\n"),
                Comp.Plain(f"失败原因：{error_msg}\n"),
                Comp.Plain(f"黑名单原因：{reason}" if reason else "黑名单用户"),
            ]
        return chain


class NotificationManager:
    """通知管理器 - 防刷屏机制"""
    
    def __init__(self, cooldown: int = 30):
        """
        Args:
            cooldown: 冷却时间（秒）
        """
        self.cooldown = cooldown
        # 防刷屏机制：记录最近的通知时间
        self._last_notification_time: Dict[str, float] = {}

    def should_send_notification(self, notification_key: str) -> bool:
        """检查是否应该发送通知（防刷屏机制）
        
        Args:
            notification_key: 通知的唯一标识
            
        Returns:
            bool: 是否应该发送通知
        """
        current_time = time.time()
        last_time = self._last_notification_time.get(notification_key, 0)

        if current_time - last_time >= self.cooldown:
            self._last_notification_time[notification_key] = current_time
            return True
        else:
            # 在冷却时间内，不发送通知
            logger.debug(f"通知 {notification_key} 在冷却时间内，跳过发送")
            return False


class SystemUtils:
    """系统工具类"""
    
    @staticmethod
    def is_system_notification(event) -> bool:
        """判断是否为系统通知消息"""
        try:
            # 检查是否有原始消息数据
            if not hasattr(event, "message_obj") or not event.message_obj:
                return False

            raw_message = event.message_obj.raw_message
            system_notices = ["group_increase", "group_decrease", "group_admin", "group_ban"]

            # 检查是否包含系统事件类型
            if isinstance(raw_message, dict):
                return raw_message.get("notice_type") in system_notices
            elif hasattr(raw_message, "notice_type"):
                notice_type = getattr(raw_message, "notice_type", None)
                return notice_type in system_notices

            return False
        except Exception:
            return False

    @staticmethod
    def extract_group_event_info(event):
        """提取群事件信息
        
        Returns:
            tuple: (notice_type, sub_type, user_id) 或 (None, None, None)
        """
        try:
            if not hasattr(event, "message_obj") or not event.message_obj:
                return None, None, None

            raw_message = event.message_obj.raw_message
            if not raw_message:
                return None, None, None

            notice_type = None
            sub_type = None
            user_id = None

            # 处理字典格式的原始消息
            if isinstance(raw_message, dict):
                notice_type = raw_message.get("notice_type")
                sub_type = raw_message.get("sub_type")
                user_id = raw_message.get("user_id")

            # 处理对象属性格式
            elif hasattr(raw_message, "notice_type"):
                notice_type = getattr(raw_message, "notice_type", None)
                user_id = getattr(raw_message, "user_id", None)
                sub_type = getattr(raw_message, "sub_type", None)

            return notice_type, sub_type, str(user_id) if user_id else None

        except Exception as e:
            logger.error(f"提取群事件信息失败: {e}")
            return None, None, None


class HelpTextBuilder:
    """帮助文本构建器"""
    
    @staticmethod
    def build_keyword_help() -> str:
        """构建词库管理帮助文本"""
        return """📚 词库管理帮助

管理员功能（系统管理员 或 群聊管理员）:
/sunos ck add <关键词> <回复内容> - 添加词库
/sunos ck del <序号> - 删除词库

用户功能:
/sunos ck list - 查看词库列表
/sunos ck help - 显示此帮助

说明:
- 支持换行符 \\n
- 自动检查重复关键词
- 管理员包括AstrBot系统管理员和群聊管理员"""

    @staticmethod
    def build_welcome_help() -> str:
        """构建欢迎语管理帮助文本"""
        return """👋 欢迎语管理帮助

管理员功能（系统管理员 或 群聊管理员）:
/sunos wc set <欢迎语内容> - 设置欢迎语
/sunos wc del - 删除欢迎语

用户功能:
/sunos wc show - 查看欢迎语
/sunos wc help - 显示此帮助

占位符:
{user} - @ 新成员
{group} - 群号

说明:
- 支持换行符 \\n
- 仅支持群聊使用
- 管理员包括AstrBot系统管理员和群聊管理员"""

    @staticmethod
    def build_blacklist_help() -> str:
        """构建黑名单管理帮助文本"""
        return """🚫 黑名单管理帮助

管理员功能（系统管理员 或 群聊管理员）:
/sunos bl add <user_id> [reason] - 添加黑名单
/sunos bl del <user_id> - 移除黑名单
/sunos bl scan - 扫描当前群内黑名单用户并处理

用户功能:
/sunos bl list - 查看黑名单列表
/sunos bl check <user_id> - 检查用户状态
/sunos bl help - 显示此帮助

说明:
- 黑名单用户入群时会被自动踢出（需要机器人有管理员权限）
- 用户退群或被踢时会自动加入群黑名单
- 扫描功能仅检查当前群内成员，已退群用户不会显示
- 支持全局黑名单（系统管理员）和群组黑名单（群管理员）
- 全局黑名单对所有群聊有效
- 群组黑名单仅对当前群聊有效
- 防刷屏机制：相同类型通知30秒内只发送一次"""