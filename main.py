"""SunOS 群聊管理插件 - 现代化模块架构

基于 AstrBot 最佳实践的模块化重构：
- 核心功能模块化：数据库、权限、平台、服务分离
- 装饰器驱动：简化权限验证和参数检查
- 事件处理器：专门处理群事件和自动回复
- 统一工具类：消息构建、验证、通知管理

架构优势：
- 清晰的职责分离
- 便于单元测试
- 高代码复用性
- 符合AstrBot设计理念
"""

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入核心模块
from .core import (
    SunosDatabase,
    PlatformAdapter,
    KeywordService,
    WelcomeService,
    BlacklistService,
    GroupService,
    GroupEventHandler,
    AutoReplyHandler,
    NotificationManager,
    ValidationUtils,
    HelpTextBuilder,
    admin_required,
    group_only,
    check_admin_permission,
    check_group_chat,
    get_user_permission_level,
    check_real_group_admin_permission,
    PermissionLevel
)


@register(
    "sunos",
    "Akuma",
    "SunOS 群聊管理插件 - 现代化模块架构",
    "2.0.0",
    "https://github.com/Akuma-real/sunos",
)
class SunosPlugin(Star):
    """SunOS 群聊管理插件主类 - 模块化重构版本"""
    
    # 错误消息常量
    ADMIN_REQUIRED_MSG = "此操作需要管理员权限（系统管理员或群管理员）"
    GROUP_ONLY_MSG = "此功能仅支持群聊"
    INVALID_PARAMS_MSG = "参数错误，使用 /sunos help 查看帮助"
    
    # 主帮助文本
    MAIN_HELP = """SunOS 群聊管理插件帮助

触发方式: /sunos 或 .sunos

📚 词库管理 (ck):
/sunos ck add <关键词> <回复内容> - 添加词库 [管理员]
/sunos ck del <序号> - 删除词库 [管理员]
/sunos ck list - 查看词库列表
/sunos ck help - 词库帮助

👋 欢迎语管理 (wc):
/sunos wc set <欢迎语> - 设置欢迎语 [管理员]
/sunos wc del - 删除欢迎语 [管理员]
/sunos wc show - 查看欢迎语
/sunos wc help - 欢迎语帮助

🚫 黑名单管理 (bl):
/sunos bl add <user_id> [reason] - 添加黑名单 [管理员]
/sunos bl del <user_id> - 移除黑名单 [管理员]
/sunos bl list - 查看黑名单列表
/sunos bl check <user_id> - 检查用户状态
/sunos bl scan - 扫描当前群内黑名单用户 [管理员]
/sunos bl help - 黑名单帮助

⚙️ 群聊开关:
/sunos enable - 开启功能 [管理员]
/sunos disable - 关闭功能 [管理员]
/sunos status - 查看状态（含权限信息）

权限说明:
[管理员] = 系统管理员 或 群聊管理员
占位符: {user} - @ 新成员, {group} - 群号
注: 所有 /sunos 命令都可以用 .sunos 替代"""

    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化核心组件
        self.db = SunosDatabase()
        self.platform_adapter = PlatformAdapter(context)
        self.notification_manager = NotificationManager(cooldown=30)
        
        # 初始化服务层
        self.keyword_service = KeywordService(self.db)
        self.welcome_service = WelcomeService(self.db)
        self.blacklist_service = BlacklistService(self.db)
        self.group_service = GroupService(self.db)
        
        # 初始化事件处理器
        self.group_event_handler = GroupEventHandler(
            self.blacklist_service,
            self.welcome_service,
            self.platform_adapter,
            self.notification_manager
        )
        self.auto_reply_handler = AutoReplyHandler(
            self.keyword_service,
            self.group_service
        )
        
        logger.info("SunOS 插件 v2.0 初始化完成 - 模块化架构")

    # ==================== 主命令处理 ====================
    
    async def _process_sunos_command(self, event: AstrMessageEvent):
        """统一处理sunos命令逻辑 - 支持多种触发方式(/sunos 和 .sunos)"""
        try:
            message_parts = event.message_str.strip().split()
            
            if len(message_parts) < 2:
                yield event.plain_result(self.MAIN_HELP)
                return
            
            action = message_parts[1]
            
            # 词库管理
            if action == "ck":
                async for result in self._handle_keyword_commands(event, message_parts):
                    yield result
            # 欢迎语管理
            elif action == "wc":
                async for result in self._handle_welcome_commands(event, message_parts):
                    yield result
            # 黑名单管理
            elif action == "bl":
                async for result in self._handle_blacklist_commands(event, message_parts):
                    yield result
            # 群聊开关管理
            elif action in ["enable", "disable", "status"]:
                async for result in self._handle_group_commands(event, action):
                    yield result
            elif action == "help":
                yield event.plain_result(self.MAIN_HELP)
            else:
                yield event.plain_result("未知操作，使用 /sunos 或 .sunos help 查看帮助")
                
        except Exception as e:
            logger.error(f"处理sunos命令失败: {e}")
            yield event.plain_result("命令处理失败，请稍后重试")
    
    @filter.command("sunos")
    async def sunos_main(self, event: AstrMessageEvent):
        """SunOS 群聊管理插件主命令 - /sunos 触发"""
        async for result in self._process_sunos_command(event):
            yield result

    # ==================== 词库管理命令 ====================
    
    async def _handle_keyword_commands(self, event: AstrMessageEvent, message_parts: list):
        """处理词库管理命令"""
        if not ValidationUtils.validate_params(message_parts, 3):
            yield event.plain_result("用法: /sunos ck <add|del|list|help>")
            return

        subaction = message_parts[2]

        if subaction == "add":
            async for result in self._handle_keyword_add(event, message_parts):
                yield result
        elif subaction == "del":
            async for result in self._handle_keyword_delete(event, message_parts):
                yield result
        elif subaction == "list":
            success, message = self.keyword_service.get_keyword_list()
            if success:
                yield event.plain_result(message)
            else:
                yield event.plain_result(message)
        elif subaction == "help":
            yield event.plain_result(HelpTextBuilder.build_keyword_help())
        else:
            yield event.plain_result("未知操作，使用 /sunos ck help 查看帮助")

    @admin_required
    async def _handle_keyword_add(self, event: AstrMessageEvent, message_parts: list):
        """添加词库"""
        if not ValidationUtils.validate_params(message_parts, 5):
            yield event.plain_result("用法: /sunos ck add <关键词> <回复内容>")
            return

        keyword = message_parts[3]
        reply = " ".join(message_parts[4:])
        
        success, message = self.keyword_service.add_keyword(keyword, reply)
        yield event.plain_result(message)

    @admin_required
    async def _handle_keyword_delete(self, event: AstrMessageEvent, message_parts: list):
        """删除词库"""
        if not ValidationUtils.validate_params(message_parts, 4):
            yield event.plain_result("用法: /sunos ck del <序号>")
            return

        try:
            index = int(message_parts[3])
        except ValueError:
            yield event.plain_result("序号必须是数字")
            return

        success, message = self.keyword_service.delete_keyword(index)
        yield event.plain_result(message)

    # ==================== 欢迎语管理命令 ====================
    
    async def _handle_welcome_commands(self, event: AstrMessageEvent, message_parts: list):
        """处理欢迎语管理命令"""
        if not ValidationUtils.validate_params(message_parts, 3):
            yield event.plain_result("用法: /sunos wc <set|del|show|help>")
            return

        subaction = message_parts[2]

        if subaction == "set":
            async for result in self._handle_welcome_set(event, message_parts):
                yield result
        elif subaction == "del":
            async for result in self._handle_welcome_delete(event, message_parts):
                yield result
        elif subaction == "show":
            async for result in self._handle_welcome_show(event, message_parts):
                yield result
        elif subaction == "help":
            yield event.plain_result(HelpTextBuilder.build_welcome_help())
        else:
            yield event.plain_result("未知操作，使用 /sunos wc help 查看帮助")

    @admin_required
    @group_only
    async def _handle_welcome_set(self, event: AstrMessageEvent, message_parts: list):
        """设置欢迎语"""
        if not ValidationUtils.validate_params(message_parts, 4):
            yield event.plain_result("用法: /sunos wc set <欢迎语内容>")
            return

        welcome_msg = " ".join(message_parts[3:])
        group_id = event.get_group_id()
        
        success, message = self.welcome_service.set_welcome_message(group_id, welcome_msg)
        yield event.plain_result(message)

    @admin_required
    @group_only
    async def _handle_welcome_delete(self, event: AstrMessageEvent, message_parts: list):
        """删除欢迎语"""
        group_id = event.get_group_id()
        success, message = self.welcome_service.delete_welcome_message(group_id)
        yield event.plain_result(message)

    @group_only
    async def _handle_welcome_show(self, event: AstrMessageEvent, message_parts: list):
        """查看欢迎语"""
        group_id = event.get_group_id()
        success, message = self.welcome_service.get_welcome_message(group_id)
        yield event.plain_result(message)

    # ==================== 黑名单管理命令 ====================
    
    async def _handle_blacklist_commands(self, event: AstrMessageEvent, message_parts: list):
        """处理黑名单管理命令"""
        if not ValidationUtils.validate_params(message_parts, 3):
            yield event.plain_result("用法: /sunos bl <add|del|list|check|scan|help>")
            return

        subaction = message_parts[2]

        if subaction == "add":
            async for result in self._handle_blacklist_add(event, message_parts):
                yield result
        elif subaction == "del":
            async for result in self._handle_blacklist_delete(event, message_parts):
                yield result
        elif subaction == "list":
            group_id = event.get_group_id()
            success, message = self.blacklist_service.get_blacklist(group_id)
            yield event.plain_result(message)
        elif subaction == "check":
            async for result in self._handle_blacklist_check(event, message_parts):
                yield result
        elif subaction == "scan":
            async for result in self._handle_blacklist_scan(event, message_parts):
                yield result
        elif subaction == "help":
            yield event.plain_result(HelpTextBuilder.build_blacklist_help())
        else:
            yield event.plain_result("未知操作，使用 /sunos bl help 查看帮助")

    @admin_required
    async def _handle_blacklist_add(self, event: AstrMessageEvent, message_parts: list):
        """添加黑名单"""
        if not ValidationUtils.validate_params(message_parts, 4):
            yield event.plain_result("用法: /sunos bl add <user_id> [reason]")
            return

        user_id = message_parts[3]
        reason = " ".join(message_parts[4:]) if len(message_parts) > 4 else ""
        
        group_id = event.get_group_id()
        added_by = event.get_sender_id()

        # 检查权限：全局黑名单需要系统管理员权限
        permission_level = get_user_permission_level(event)
        if group_id is None and permission_level != PermissionLevel.SUPER_ADMIN:
            yield event.plain_result("添加全局黑名单需要系统管理员权限")
            return

        success, message = self.blacklist_service.add_user_to_blacklist(
            user_id, added_by, group_id, reason
        )
        yield event.plain_result(message)

    @admin_required
    async def _handle_blacklist_delete(self, event: AstrMessageEvent, message_parts: list):
        """删除黑名单"""
        if not ValidationUtils.validate_params(message_parts, 4):
            yield event.plain_result("用法: /sunos bl del <user_id>")
            return

        user_id = message_parts[3]
        group_id = event.get_group_id()

        # 检查权限：全局黑名单需要系统管理员权限
        permission_level = get_user_permission_level(event)
        if group_id is None and permission_level != PermissionLevel.SUPER_ADMIN:
            yield event.plain_result("操作全局黑名单需要系统管理员权限")
            return

        success, message = self.blacklist_service.remove_user_from_blacklist(user_id, group_id)
        yield event.plain_result(message)

    async def _handle_blacklist_check(self, event: AstrMessageEvent, message_parts: list):
        """检查黑名单状态"""
        if not ValidationUtils.validate_params(message_parts, 4):
            yield event.plain_result("用法: /sunos bl check <user_id>")
            return

        user_id = message_parts[3]
        group_id = event.get_group_id()

        is_blacklisted, message = self.blacklist_service.check_user_blacklist_status(user_id, group_id)
        yield event.plain_result(message)

    @admin_required
    @group_only
    async def _handle_blacklist_scan(self, event: AstrMessageEvent, message_parts: list):
        """扫描群内黑名单用户"""
        yield event.plain_result("正在扫描群内黑名单用户，请稍候...")
        
        # 使用平台适配器扫描
        success, result_msg = await self.platform_adapter.scan_group_for_blacklist(
            event, self.blacklist_service.is_user_blacklisted
        )
        
        if success and "发现" in result_msg and "个黑名单用户" in result_msg:
            # 如果发现了黑名单用户，需要进一步处理踢人
            group_id = event.get_group_id()
            group_members = await self.platform_adapter.get_group_member_list(event, group_id)
            
            if group_members:
                found_users = []
                for user_id in group_members:
                    if self.blacklist_service.is_user_blacklisted(str(user_id), group_id):
                        found_users.append(str(user_id))
                
                if found_users:
                    kicked_count = 0
                    failed_count = 0
                    error_details = []
                    
                    for user_id in found_users:
                        # 获取黑名单详情
                        blacklist_info = self.blacklist_service.get_user_blacklist_info(user_id, group_id)
                        reason = ""
                        if blacklist_info:
                            _, _, bl_group_id, bl_reason, added_by, created_at = blacklist_info
                            reason = bl_reason if bl_reason else "黑名单用户"
                        
                        success, msg = await self.platform_adapter.kick_user_from_group(
                            event, user_id, f"黑名单用户：{reason}"
                        )
                        if success:
                            kicked_count += 1
                        else:
                            failed_count += 1
                            error_details.append(f"用户 {user_id}: {msg}")
                    
                    # 生成详细的结果报告
                    result_msg = f"群内扫描完成，检查了 {len(group_members)} 名成员\n"
                    result_msg += f"发现黑名单用户：{len(found_users)} 个\n"
                    result_msg += f"成功处理：{kicked_count} 个\n"
                    if failed_count > 0:
                        result_msg += f"处理失败：{failed_count} 个\n"
                        if error_details:
                            result_msg += "失败详情：\n" + "\n".join(error_details[:3])
                            if len(error_details) > 3:
                                result_msg += f"\n... 还有 {len(error_details) - 3} 个错误"
        
        yield event.plain_result(result_msg)

    # ==================== 群聊开关管理 ====================
    
    async def _handle_group_commands(self, event: AstrMessageEvent, action: str):
        """处理群聊开关命令"""
        if action in ["enable", "disable"]:
            async for result in self._handle_group_toggle(event, action):
                yield result
        elif action == "status":
            async for result in self._handle_group_status(event):
                yield result

    @admin_required
    @group_only
    async def _handle_group_toggle(self, event: AstrMessageEvent, action: str):
        """切换群聊开关"""
        group_id = event.get_group_id()
        enabled = action == "enable"
        
        success, message = self.group_service.set_group_enabled(group_id, enabled)
        yield event.plain_result(message)

    @group_only
    async def _handle_group_status(self, event: AstrMessageEvent):
        """查看群聊状态"""
        group_id = event.get_group_id()
        
        # 首先尝试使用异步API检查真实权限
        real_admin_status = False
        api_check_success = False
        
        try:
            real_admin_status = await check_real_group_admin_permission(event, group_id)
            api_check_success = True
            logger.info(f"异步API权限检查结果: {real_admin_status}")
        except Exception as e:
            logger.debug(f"异步API权限检查失败: {e}")
        
        # 获取基础权限级别
        user_permission = get_user_permission_level(event)
        
        # 确定最终权限显示文本
        if user_permission == PermissionLevel.SUPER_ADMIN:
            permission_text = "🔒 系统管理员"
        elif real_admin_status and api_check_success:
            permission_text = "👑 群聊管理员 (API确认)"
        elif user_permission == PermissionLevel.GROUP_ADMIN:
            permission_text = "👑 群聊管理员"
        else:
            permission_text = "👤 普通用户"
        
        # 添加调试信息
        logger.info(f"权限检测结果 - 用户:{event.get_sender_id()}, 群:{group_id}, "
                   f"基础权限:{user_permission}, API结果:{real_admin_status}, "
                   f"最终显示:{permission_text}")

        keywords_count = len(self.keyword_service.db.get_all_keywords())
        
        status_message = self.group_service.get_group_status(
            group_id, permission_text, keywords_count
        )
        
        yield event.plain_result(status_message)

    # ==================== 事件处理 ====================
    
    @filter.event_message_type(filter.EventMessageType.ALL, priority=1)
    async def handle_all_events(self, event: AstrMessageEvent):
        """统一事件处理入口 - 处理 .sunos 命令、自动回复和群事件"""
        try:
            # 优先处理 .sunos 命令（避免与其他功能冲突）
            message_text = event.message_str.strip()
            if message_text.startswith(".sunos"):
                # 将 .sunos 命令路由到统一的命令处理逻辑
                async for result in self._process_sunos_command(event):
                    yield result
                return  # .sunos 命令处理完成后直接返回，避免触发其他处理逻辑
            
            # 处理群事件（入群/退群）
            async for result in self.group_event_handler.handle_group_events(event):
                yield result
            
            # 处理自动回复
            async for result in self.auto_reply_handler.handle_auto_reply(event):
                yield result
            
        except Exception as e:
            logger.error(f"统一事件处理失败: {e}")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("SunOS 插件 v2.0 已卸载 - 模块化架构")