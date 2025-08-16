"""平台适配模块 - 处理平台特定操作

统一不同平台的API调用，提供平台无关的操作接口
"""
from typing import List, Optional, Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.api import logger


class PlatformAdapter:
    """平台适配器 - 统一平台操作接口"""
    
    def __init__(self, context: Context):
        self.context = context

    def is_platform_supported(
        self, event: AstrMessageEvent, required_platform: str = "aiocqhttp"
    ) -> bool:
        """检查当前平台是否支持特定功能
        
        Args:
            event: 消息事件
            required_platform: 需要的平台名称
            
        Returns:
            bool: 是否支持
        """
        platform_name = event.get_platform_name()
        if platform_name != required_platform:
            logger.debug(
                f"当前平台 {platform_name} 不支持此功能，需要 {required_platform}"
            )
            return False
        return True

    def get_platform_instance(self, platform_name: str = "aiocqhttp"):
        """获取指定平台实例的通用方法
        
        Args:
            platform_name: 平台名称，默认为 aiocqhttp
            
        Returns:
            平台实例对象，如果未找到则返回 None
        """
        try:
            platform_mgr = self.context.platform_manager
            if not platform_mgr:
                logger.warning("无法获取到平台管理器")
                return None

            # 遍历所有平台实例，查找匹配的平台
            for platform in platform_mgr.platform_insts:
                if platform.metadata.name == platform_name:
                    return platform

            logger.warning(f"未找到 {platform_name} 平台实例")
            return None

        except Exception as e:
            logger.error(f"获取平台实例失败: {e}")
            return None

    async def is_bot_group_admin(self, event: AstrMessageEvent, group_id: str) -> bool:
        """检查机器人是否为群管理员
        
        Args:
            event: 消息事件
            group_id: 群组ID
            
        Returns:
            bool: 机器人是否为群管理员
        """
        try:
            # 检查平台支持
            if not self.is_platform_supported(event, "aiocqhttp"):
                return False

            # 获取平台实例
            platform_instance = self.get_platform_instance("aiocqhttp")
            if not platform_instance or not hasattr(platform_instance, "bot"):
                logger.warning("无法获取到有效的平台实例")
                return False

            # 调用 OneBot API 获取群信息
            response = await platform_instance.bot.call_action(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(platform_instance.bot.self_id),
            )

            if response and isinstance(response, dict):
                role = response.get("role", "member")
                # 管理员权限：owner（群主）或 admin（管理员）
                is_admin = role in ["owner", "admin"]
                logger.info(
                    f"机器人在群 {group_id} 的角色: {role}, 是否为管理员: {is_admin}"
                )
                return is_admin
            else:
                logger.warning(f"获取机器人群权限信息失败: {response}")
                return False

        except Exception as e:
            logger.error(f"检查机器人群管理员权限失败: {e}")
            return False

    async def kick_user_from_group(
        self, event: AstrMessageEvent, user_id: str, reason: str = ""
    ) -> Tuple[bool, str]:
        """踢出群成员
        
        Args:
            event: 消息事件
            user_id: 要踢出的用户ID
            reason: 踢出原因
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        try:
            group_id = event.get_group_id()
            if not group_id:
                return False, "此功能仅支持群聊"

            reason_text = f"，原因：{reason}" if reason else ""

            # 检查平台支持
            if not self.is_platform_supported(event, "aiocqhttp"):
                platform_name = event.get_platform_name()
                return (
                    False,
                    f"当前平台 ({platform_name}) 暂不支持自动踢人功能{reason_text}",
                )

            # 检查机器人是否为群管理员
            is_bot_admin = await self.is_bot_group_admin(event, group_id)
            if not is_bot_admin:
                logger.warning(
                    f"机器人不是群 {group_id} 的管理员，无法踢出用户 {user_id}"
                )
                return (
                    False,
                    f"机器人无管理员权限，无法踢出用户{reason_text}",
                )

            # 获取平台实例并调用踢人API
            platform_instance = self.get_platform_instance("aiocqhttp")
            if not platform_instance or not hasattr(platform_instance, "bot"):
                return (
                    False,
                    f"无法访问踢人接口{reason_text}，请联系管理员手动处理",
                )

            # 调用 OneBot API 踢出用户
            await platform_instance.bot.call_action(
                "set_group_kick",
                group_id=int(group_id),
                user_id=int(user_id),
                reject_add_request=False,  # 不拒绝此人的加群请求
            )
            logger.info(f"成功踢出用户 {user_id} 从群 {group_id}{reason_text}")
            return True, f"已成功踢出用户 {user_id}{reason_text}"

        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            return False, f"踢人操作失败{reason_text}，请联系管理员手动处理"

    async def get_group_member_list(
        self, event: AstrMessageEvent, group_id: str
    ) -> List[str]:
        """获取群成员列表
        
        Args:
            event: 消息事件
            group_id: 群组ID
            
        Returns:
            list: 群成员ID列表
        """
        try:
            # 检查平台支持
            if not self.is_platform_supported(event, "aiocqhttp"):
                platform_name = event.get_platform_name()
                logger.warning(f"平台 {platform_name} 暂不支持获取群成员列表")
                return []

            # 获取平台实例
            platform_instance = self.get_platform_instance("aiocqhttp")
            if not platform_instance or not hasattr(platform_instance, "bot"):
                logger.warning("无法获取到有效的平台实例")
                return []

            logger.info(f"正在调用 OneBot API 获取群 {group_id} 成员列表...")

            # 调用 OneBot API 获取群成员列表
            response = await platform_instance.bot.call_action(
                "get_group_member_list", group_id=int(group_id)
            )

            logger.debug(
                f"API 响应类型: {type(response)}, 响应长度: {len(response) if isinstance(response, list) else 'N/A'}"
            )

            if not response or not isinstance(response, list):
                logger.warning(f"获取群成员列表返回数据异常: {response}")
                return []

            # 提取用户ID列表
            member_ids = []
            for i, member in enumerate(response):
                if isinstance(member, dict) and "user_id" in member:
                    user_id = str(member["user_id"])
                    member_ids.append(user_id)
                    if i < 5:  # 只显示前5个成员的详细信息
                        logger.debug(
                            f"成员 {i + 1}: {user_id} ({member.get('nickname', 'unknown')})"
                        )
                else:
                    logger.warning(f"成员数据格式异常: {member}")

            logger.info(f"成功获取群 {group_id} 成员列表，共 {len(member_ids)} 名成员")
            return member_ids

        except Exception as e:
            logger.error(f"获取群成员列表失败: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    async def scan_group_for_blacklist(
        self, event: AstrMessageEvent, blacklist_checker_func
    ) -> Tuple[bool, str]:
        """扫描群内黑名单用户
        
        Args:
            event: 消息事件
            blacklist_checker_func: 黑名单检查函数
            
        Returns:
            tuple: (是否成功, 结果消息)
        """
        try:
            group_id = event.get_group_id()
            if not group_id:
                return False, "此功能仅支持群聊"

            # 获取群成员列表
            group_members = await self.get_group_member_list(event, group_id)
            if not group_members:
                return False, "无法获取群成员列表，请稍后重试"

            logger.info(f"开始扫描群 {group_id}，共 {len(group_members)} 名成员")

            # 检查每个群成员是否在黑名单中
            found_users = []
            logger.info(f"开始检查 {len(group_members)} 名群成员的黑名单状态...")

            for i, user_id in enumerate(group_members):
                # 使用传入的检查函数
                is_blacklisted = blacklist_checker_func(str(user_id), group_id)
                if is_blacklisted:
                    found_users.append(str(user_id))
                    logger.info(f"发现黑名单用户: {user_id}")
                else:
                    # 只记录前几个检查结果，避免日志过多
                    if i < 5:
                        logger.info(f"用户 {user_id} 不在黑名单中")

            logger.info(f"黑名单检查完成，发现 {len(found_users)} 个黑名单用户")

            if not found_users:
                return (
                    True,
                    f"群内扫描完成（{len(group_members)} 名成员），当前群内无黑名单用户\n"
                    f"注意：扫描仅检查当前群内成员，已退群的黑名单用户不会显示",
                )

            return True, f"发现 {len(found_users)} 个黑名单用户: {found_users}"

        except Exception as e:
            logger.error(f"扫描群内黑名单失败: {e}")
            return False, "扫描群内黑名单失败，请稍后重试"