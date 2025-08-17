"""事件处理器模块 - 专门处理群事件和自动回复

分离事件处理逻辑，提供清晰的事件处理接口
"""
from typing import Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from .services import BlacklistService, WelcomeService, GroupService
from .platform import PlatformAdapter
from .utils import (
    SystemUtils, 
    MessageBuilder, 
    NotificationManager
)
import astrbot.api.message_components as Comp


class GroupEventHandler:
    """群事件处理器 - 处理入群/退群事件"""
    
    def __init__(
        self, 
        blacklist_service: BlacklistService,
        welcome_service: WelcomeService,
        platform_adapter: PlatformAdapter,
        notification_manager: NotificationManager
    ):
        self.blacklist_service = blacklist_service
        self.welcome_service = welcome_service
        self.platform_adapter = platform_adapter
        self.notification_manager = notification_manager

    async def handle_group_events(self, event: AstrMessageEvent):
        """统一群事件处理入口"""
        try:
            group_id = event.get_group_id()
            if not group_id:
                return

            # 检测群事件
            notice_type, sub_type, user_id = SystemUtils.extract_group_event_info(event)
            
            if notice_type not in ["group_increase", "group_decrease"]:
                return

            if not user_id:
                return

            # 处理入群事件
            if notice_type == "group_increase":
                logger.info(f"处理入群事件: 群 {group_id}, 用户 {user_id}")
                async for result in self.handle_member_join(event, group_id, user_id):
                    yield result

            # 处理退群事件
            elif notice_type == "group_decrease":
                logger.info(f"处理退群事件: 群 {group_id}, 用户 {user_id}, 类型 {sub_type}")
                async for result in self.handle_member_leave(event, group_id, user_id, str(sub_type or "unknown")):
                    yield result

        except Exception as e:
            logger.error(f"处理群事件失败: {e}")

    async def handle_member_join(self, event: AstrMessageEvent, group_id: str, user_id: str):
        """处理成员入群事件
        
        执行流程：
        1. 验证用户ID是否有效
        2. 检查用户是否在黑名单中
        3. 如果在黑名单，尝试踢出并发送通知
        4. 如果不在黑名单，发送欢迎消息
        
        Args:
            event: 消息事件对象
            group_id: 群组ID
            user_id: 加入群聊的用户ID
        """
        if not user_id:
            return

        # 首先检查黑名单 - 优先处理安全问题
        if self.blacklist_service.is_user_blacklisted(user_id, group_id):
            logger.info(f"检测到黑名单用户 {user_id} 尝试加入群聊 {group_id}")

            # 获取黑名单详细信息，用于踢出原因和日志记录
            blacklist_info = self.blacklist_service.get_user_blacklist_info(user_id, group_id)
            reason = ""
            if blacklist_info:
                _, _, bl_group_id, bl_reason, added_by, created_at = blacklist_info
                reason = bl_reason if bl_reason else "黑名单用户"
                scope_text = "全局黑名单" if bl_group_id is None else "群组黑名单"
                logger.info(f"用户 {user_id} 在{scope_text}中，原因：{reason}，添加者：{added_by}")

            # 尝试踢出用户 - 调用平台适配器执行踢人操作
            success, kick_msg = await self.platform_adapter.kick_user_from_group(
                event, user_id, f"黑名单用户：{reason}"
            )

            # 使用防刷屏机制，避免频繁通知消息刷屏
            notification_key = f"blacklist_join_{group_id}"
            should_notify = self.notification_manager.should_send_notification(notification_key)

            if should_notify:
                # 构建并发送黑名单用户处理通知消息
                chain = MessageBuilder.build_blacklist_notification(
                    user_id, success, reason, kick_msg if not success else ""
                )
                yield event.chain_result(chain)
                
            if success:
                logger.info(f"成功踢出黑名单用户 {user_id}")
            else:
                logger.warning(f"踢出黑名单用户 {user_id} 失败: {kick_msg}")

            # 无论踢出是否成功，都不发送欢迎语
            return

        # 非黑名单用户，正常处理欢迎语
        welcome_msg = self.welcome_service.get_welcome_message_raw(group_id)

        if welcome_msg:
            # 构建消息链，正确处理占位符
            chain = MessageBuilder.build_welcome_chain(welcome_msg, user_id, group_id)
            yield event.chain_result(chain)
        else:
            # 默认欢迎语
            chain = [Comp.At(qq=user_id), Comp.Plain(" 欢迎加入群聊！")]
            yield event.chain_result(chain)

        logger.info(f"用户 {user_id} 加入了群聊 {group_id}")

    async def handle_member_leave(
        self, event: AstrMessageEvent, group_id: str, user_id: str, sub_type: str
    ):
        """处理成员退群"""
        # 根据退群类型记录日志和发送通知
        reason_map = {
            "leave": "主动退群",
            "kick": "被踢出群", 
            "kick_me": None,  # 机器人被踢，无需处理
        }
        reason = reason_map.get(sub_type, f"离开群聊({sub_type})")
        
        if reason is None:  # 机器人被踢出
            logger.info(f"机器人被踢出了群聊 {group_id}")
            return

        notification_msg = f"用户 {user_id} 离开了群聊"
        
        logger.info(f"用户 {user_id} {reason} {group_id}")

        # 自动加入群黑名单
        if reason:  # 确保有原因记录
            try:
                # 检查用户是否已在黑名单中
                if not self.blacklist_service.is_user_blacklisted(user_id, group_id):
                    # 使用系统自动添加标识
                    success, msg = self.blacklist_service.add_user_to_blacklist(
                        user_id, "system_auto", group_id, reason
                    )
                    if success:
                        logger.info(f"已自动将用户 {user_id} 加入群 {group_id} 黑名单，原因：{reason}")
                        notification_msg += "，已自动加入群黑名单"
                    else:
                        logger.warning(f"自动加入黑名单失败：用户 {user_id}")
                        notification_msg += "，加入黑名单失败"
                else:
                    logger.info(f"用户 {user_id} 已在群 {group_id} 黑名单中，跳过自动添加")
                    notification_msg += "，已在群黑名单中"

            except Exception as e:
                logger.error(f"自动加入黑名单时发生错误: {e}")
                notification_msg += "，加入黑名单时出错"

        # 使用防刷屏机制发送退群通知
        notification_key = f"member_leave_{group_id}"
        should_notify = self.notification_manager.should_send_notification(notification_key)

        if should_notify:
            yield event.plain_result(notification_msg)
        else:
            # 在冷却期内，只记录日志不发送通知
            logger.info(f"退群通知在冷却期内，跳过发送: {notification_msg}")


class AutoReplyHandler:
    """自动回复处理器 - 处理关键词匹配回复"""
    
    def __init__(self, keyword_service, group_service):
        self.keyword_service = keyword_service
        self.group_service = group_service

    async def handle_auto_reply(self, event: AstrMessageEvent):
        """处理自动回复功能"""
        try:
            # 跳过指令消息、唤醒消息和系统通知
            if event.is_at_or_wake_command or SystemUtils.is_system_notification(event):
                return

            # 只处理有文本内容的消息
            if not event.message_str or not event.message_str.strip():
                return

            group_id = event.get_group_id()

            # 检查群聊是否开启功能
            if group_id and not self.group_service.is_group_enabled(group_id):
                return

            # 精确匹配关键词
            message_text = event.message_str.strip()
            reply = self.keyword_service.find_keyword_reply(message_text)
            
            if reply:
                yield event.plain_result(reply)
                event.stop_event()  # 停止事件传播，避免触发其他处理
                
        except Exception as e:
            logger.error(f"自动回复处理失败: {e}")