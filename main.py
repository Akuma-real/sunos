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
    ERROR_ADMIN_REQUIRED = "此操作需要管理员权限（系统管理员或群管理员）"
    ERROR_GROUP_ONLY = "此功能仅支持群聊"
    ERROR_INVALID_PARAMS = "参数错误，使用 /sunos help 查看帮助"
    ERROR_COMMAND_FAILED = "命令处理失败，请稍后重试"
    ERROR_UNKNOWN_ACTION = "未知操作，使用 /sunos 或 .sunos help 查看帮助"
    
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

    # ==================== 通用工具方法 ====================
    
    def _handle_service_result(self, event: AstrMessageEvent, service_result: tuple):
        """通用服务结果处理方法
        
        Args:
            event: 消息事件对象
            service_result: 服务层返回的 (is_success, message) 元组
            
        Returns:
            消息事件结果
        """
        _, response_message = service_result
        return event.plain_result(response_message)
    
    def _yield_usage_message(self, event: AstrMessageEvent, usage_text: str):
        """生成并发送使用说明消息
        
        Args:
            event: 消息事件对象
            usage_text: 使用说明文本
        """
        yield event.plain_result(f"用法: {usage_text}")
    
    def _validate_command_params(self, event: AstrMessageEvent, command_args: list, 
                                min_params: int, usage_message: str) -> bool:
        """通用命令参数验证方法
        
        Args:
            event: 消息事件对象
            command_args: 命令参数列表
            min_params: 最少参数数量
            usage_message: 使用说明消息
            
        Returns:
            验证是否通过
        """
        if not ValidationUtils.validate_params(command_args, min_params):
            # 这里我们不能直接yield，需要调用者处理
            return False
        return True
    
    def _create_unknown_action_message(self, command_group: str) -> str:
        """生成未知操作错误消息
        
        Args:
            command_group: 命令组名（如 ck, wc, bl）
            
        Returns:
            错误消息字符串
        """
        return f"未知操作，使用 /sunos {command_group} help 查看帮助"

    # ==================== 主命令处理 ====================
    
    async def _process_sunos_command(self, event: AstrMessageEvent):
        """统一处理sunos命令逻辑 - 支持多种触发方式(/sunos 和 .sunos)"""
        try:
            command_args = event.message_str.strip().split()
            
            if len(command_args) < 2:
                yield event.plain_result(self.MAIN_HELP)
                return
            
            main_action = command_args[1]
            
            # 词库管理
            if main_action == "ck":
                async for result in self._process_keyword_commands(event, command_args):
                    yield result
            # 欢迎语管理
            elif main_action == "wc":
                async for result in self._process_welcome_commands(event, command_args):
                    yield result
            # 黑名单管理
            elif main_action == "bl":
                async for result in self._process_blacklist_commands(event, command_args):
                    yield result
            # 群聊开关管理
            elif main_action in ["enable", "disable", "status"]:
                async for result in self._process_group_commands(event, main_action):
                    yield result
            elif main_action == "help":
                yield event.plain_result(self.MAIN_HELP)
            else:
                yield event.plain_result(self.ERROR_UNKNOWN_ACTION)
                
        except Exception as e:
            logger.error(f"处理sunos命令失败: {e}")
            yield event.plain_result(self.ERROR_COMMAND_FAILED)
    
    @filter.command("sunos")
    async def sunos_main(self, event: AstrMessageEvent):
        """SunOS 群聊管理插件主命令 - /sunos 触发"""
        async for result in self._process_sunos_command(event):
            yield result

    @filter.command_group("sunos")
    async def sunos_dot_main(self, event: AstrMessageEvent):
        """SunOS 群聊管理插件点命令 - .sunos 触发"""
        async for result in self._process_sunos_command(event):
            yield result

    # ==================== 词库管理命令 ====================
    
    async def _process_keyword_commands(self, event: AstrMessageEvent, command_args: list):
        """处理词库管理命令"""
        if not ValidationUtils.validate_params(command_args, 3):
            async for result in self._yield_usage_message(event, "/sunos ck <add|del|list|help>"):
                yield result
            return

        sub_command = command_args[2]

        if sub_command == "add":
            async for result in self._process_keyword_add(event, command_args):
                yield result
        elif sub_command == "del":
            async for result in self._process_keyword_delete(event, command_args):
                yield result
        elif sub_command == "list":
            service_result = self.keyword_service.get_keyword_list()
            yield self._handle_service_result(event, service_result)
        elif sub_command == "help":
            yield event.plain_result(HelpTextBuilder.build_keyword_help())
        else:
            yield event.plain_result(self._create_unknown_action_message("ck"))

    @admin_required
    async def _process_keyword_add(self, event: AstrMessageEvent, command_args: list):
        """添加词库"""
        if not ValidationUtils.validate_params(command_args, 5):
            async for result in self._yield_usage_message(event, "/sunos ck add <关键词> <回复内容>"):
                yield result
            return

        keyword_text = command_args[3]
        reply_content = " ".join(command_args[4:])
        
        is_success, response_message = self.keyword_service.add_keyword(keyword_text, reply_content)
        yield self._handle_service_result(event, (is_success, response_message))

    @admin_required
    async def _process_keyword_delete(self, event: AstrMessageEvent, command_args: list):
        """删除词库"""
        if not ValidationUtils.validate_params(command_args, 4):
            async for result in self._yield_usage_message(event, "/sunos ck del <序号>"):
                yield result
            return

        try:
            keyword_index = int(command_args[3])
        except ValueError:
            yield event.plain_result("序号必须是数字")
            return

        is_success, response_message = self.keyword_service.delete_keyword(keyword_index)
        yield self._handle_service_result(event, (is_success, response_message))

    # ==================== 欢迎语管理命令 ====================
    
    async def _process_welcome_commands(self, event: AstrMessageEvent, command_args: list):
        """处理欢迎语管理命令"""
        if not ValidationUtils.validate_params(command_args, 3):
            async for result in self._yield_usage_message(event, "/sunos wc <set|del|show|help>"):
                yield result
            return

        sub_command = command_args[2]

        if sub_command == "set":
            async for result in self._process_welcome_set(event, command_args):
                yield result
        elif sub_command == "del":
            async for result in self._process_welcome_delete(event, command_args):
                yield result
        elif sub_command == "show":
            async for result in self._process_welcome_show(event, command_args):
                yield result
        elif sub_command == "help":
            yield event.plain_result(HelpTextBuilder.build_welcome_help())
        else:
            yield event.plain_result(self._create_unknown_action_message("wc"))

    @admin_required
    @group_only
    async def _process_welcome_set(self, event: AstrMessageEvent, command_args: list):
        """设置欢迎语"""
        if not ValidationUtils.validate_params(command_args, 4):
            async for result in self._yield_usage_message(event, "/sunos wc set <欢迎语内容>"):
                yield result
            return

        welcome_message_content = " ".join(command_args[3:])
        current_group_id = event.get_group_id()
        
        service_result = self.welcome_service.set_welcome_message(current_group_id, welcome_message_content)
        yield self._handle_service_result(event, service_result)

    @admin_required
    @group_only
    async def _process_welcome_delete(self, event: AstrMessageEvent, command_args: list):
        """删除欢迎语"""
        current_group_id = event.get_group_id()
        service_result = self.welcome_service.delete_welcome_message(current_group_id)
        yield self._handle_service_result(event, service_result)

    @group_only
    async def _process_welcome_show(self, event: AstrMessageEvent, command_args: list):
        """查看欢迎语"""
        current_group_id = event.get_group_id()
        service_result = self.welcome_service.get_welcome_message(current_group_id)
        yield self._handle_service_result(event, service_result)

    # ==================== 黑名单管理命令 ====================
    
    async def _process_blacklist_commands(self, event: AstrMessageEvent, command_args: list):
        """处理黑名单管理命令"""
        if not ValidationUtils.validate_params(command_args, 3):
            async for result in self._yield_usage_message(event, "/sunos bl <add|del|list|check|scan|help>"):
                yield result
            return

        sub_command = command_args[2]

        if sub_command == "add":
            async for result in self._process_blacklist_add(event, command_args):
                yield result
        elif sub_command == "del":
            async for result in self._process_blacklist_delete(event, command_args):
                yield result
        elif sub_command == "list":
            current_group_id = event.get_group_id()
            service_result = self.blacklist_service.get_blacklist(current_group_id)
            yield self._handle_service_result(event, service_result)
        elif sub_command == "check":
            async for result in self._process_blacklist_check(event, command_args):
                yield result
        elif sub_command == "scan":
            async for result in self._process_blacklist_scan(event, command_args):
                yield result
        elif sub_command == "help":
            yield event.plain_result(HelpTextBuilder.build_blacklist_help())
        else:
            yield event.plain_result(self._create_unknown_action_message("bl"))

    @admin_required
    async def _process_blacklist_add(self, event: AstrMessageEvent, command_args: list):
        """添加黑名单"""
        if not ValidationUtils.validate_params(command_args, 4):
            async for result in self._yield_usage_message(event, "/sunos bl add <user_id> [reason]"):
                yield result
            return

        target_user_id = command_args[3]
        blacklist_reason = " ".join(command_args[4:]) if len(command_args) > 4 else ""
        
        current_group_id = event.get_group_id()
        operator_user_id = event.get_sender_id()

        # 检查权限：全局黑名单需要系统管理员权限
        user_permission_level = get_user_permission_level(event)
        if current_group_id is None and user_permission_level != PermissionLevel.SUPER_ADMIN:
            yield event.plain_result("添加全局黑名单需要系统管理员权限")
            return

        service_result = self.blacklist_service.add_user_to_blacklist(
            target_user_id, operator_user_id, current_group_id, blacklist_reason
        )
        yield self._handle_service_result(event, service_result)

    @admin_required
    async def _process_blacklist_delete(self, event: AstrMessageEvent, command_args: list):
        """删除黑名单"""
        if not ValidationUtils.validate_params(command_args, 4):
            async for result in self._yield_usage_message(event, "/sunos bl del <user_id>"):
                yield result
            return

        target_user_id = command_args[3]
        current_group_id = event.get_group_id()

        # 检查权限：全局黑名单需要系统管理员权限
        user_permission_level = get_user_permission_level(event)
        if current_group_id is None and user_permission_level != PermissionLevel.SUPER_ADMIN:
            yield event.plain_result("操作全局黑名单需要系统管理员权限")
            return

        service_result = self.blacklist_service.remove_user_from_blacklist(target_user_id, current_group_id)
        yield self._handle_service_result(event, service_result)

    async def _process_blacklist_check(self, event: AstrMessageEvent, command_args: list):
        """检查黑名单状态"""
        if not ValidationUtils.validate_params(command_args, 4):
            async for result in self._yield_usage_message(event, "/sunos bl check <user_id>"):
                yield result
            return

        target_user_id = command_args[3]
        current_group_id = event.get_group_id()

        service_result = self.blacklist_service.check_user_blacklist_status(target_user_id, current_group_id)
        yield self._handle_service_result(event, service_result)

    @admin_required
    @group_only
    async def _process_blacklist_scan(self, event: AstrMessageEvent, command_args: list):
        """扫描群内黑名单用户"""
        yield event.plain_result("正在扫描群内黑名单用户，请稍候...")
        
        # 使用平台适配器扫描
        scan_success, scan_result_message = await self.platform_adapter.scan_group_for_blacklist(
            event, self.blacklist_service.is_user_blacklisted
        )
        
        if scan_success and "发现" in scan_result_message and "个黑名单用户" in scan_result_message:
            # 如果发现了黑名单用户，需要进一步处理踢人
            current_group_id = event.get_group_id()
            group_member_list = await self.platform_adapter.get_group_member_list(event, current_group_id)
            
            if group_member_list:
                blacklisted_users = []
                for member_user_id in group_member_list:
                    if self.blacklist_service.is_user_blacklisted(str(member_user_id), current_group_id):
                        blacklisted_users.append(str(member_user_id))
                
                if blacklisted_users:
                    successful_kicks = 0
                    failed_kicks = 0
                    kick_error_details = []
                    
                    for blacklisted_user_id in blacklisted_users:
                        # 获取黑名单详情
                        user_blacklist_info = self.blacklist_service.get_user_blacklist_info(blacklisted_user_id, current_group_id)
                        kick_reason = ""
                        if user_blacklist_info:
                            _, _, _, blacklist_reason, _, _ = user_blacklist_info
                            kick_reason = blacklist_reason if blacklist_reason else "黑名单用户"
                        
                        kick_success, kick_message = await self.platform_adapter.kick_user_from_group(
                            event, blacklisted_user_id, f"黑名单用户：{kick_reason}"
                        )
                        if kick_success:
                            successful_kicks += 1
                        else:
                            failed_kicks += 1
                            kick_error_details.append(f"用户 {blacklisted_user_id}: {kick_message}")
                    
                    # 生成详细的结果报告
                    scan_result_message = f"群内扫描完成，检查了 {len(group_member_list)} 名成员\n"
                    scan_result_message += f"发现黑名单用户：{len(blacklisted_users)} 个\n"
                    scan_result_message += f"成功处理：{successful_kicks} 个\n"
                    if failed_kicks > 0:
                        scan_result_message += f"处理失败：{failed_kicks} 个\n"
                        if kick_error_details:
                            scan_result_message += "失败详情：\n" + "\n".join(kick_error_details[:3])
                            if len(kick_error_details) > 3:
                                scan_result_message += f"\n... 还有 {len(kick_error_details) - 3} 个错误"
        
        yield event.plain_result(scan_result_message)

    # ==================== 群聊开关管理 ====================
    
    async def _process_group_commands(self, event: AstrMessageEvent, main_action: str):
        """处理群聊开关命令"""
        if main_action in ["enable", "disable"]:
            async for result in self._process_group_toggle(event, main_action):
                yield result
        elif main_action == "status":
            async for result in self._process_group_status(event):
                yield result

    @admin_required
    @group_only
    async def _process_group_toggle(self, event: AstrMessageEvent, toggle_action: str):
        """切换群聊开关"""
        current_group_id = event.get_group_id()
        is_enabled = toggle_action == "enable"
        
        service_result = self.group_service.set_group_enabled(current_group_id, is_enabled)
        yield self._handle_service_result(event, service_result)

    @group_only
    async def _process_group_status(self, event: AstrMessageEvent):
        """查看群聊状态"""
        current_group_id = event.get_group_id()
        
        # 首先尝试使用异步API检查真实权限
        is_real_admin = False
        api_check_successful = False
        
        try:
            is_real_admin = await check_real_group_admin_permission(event, current_group_id)
            api_check_successful = True
            logger.info(f"异步API权限检查结果: {is_real_admin}")
        except Exception as e:
            logger.debug(f"异步API权限检查失败: {e}")
        
        # 获取基础权限级别
        user_permission_level = get_user_permission_level(event)
        
        # 确定最终权限显示文本
        if user_permission_level == PermissionLevel.SUPER_ADMIN:
            permission_display_text = "🔒 系统管理员"
        elif is_real_admin and api_check_successful:
            permission_display_text = "👑 群聊管理员 (API确认)"
        elif user_permission_level == PermissionLevel.GROUP_ADMIN:
            permission_display_text = "👑 群聊管理员"
        else:
            permission_display_text = "👤 普通用户"
        
        # 添加调试信息
        logger.info(f"权限检测结果 - 用户:{event.get_sender_id()}, 群:{current_group_id}, "
                   f"基础权限:{user_permission_level}, API结果:{is_real_admin}, "
                   f"最终显示:{permission_display_text}")

        total_keywords_count = len(self.keyword_service.db.get_all_keywords())
        
        group_status_message = self.group_service.get_group_status(
            current_group_id, permission_display_text, total_keywords_count
        )
        
        yield event.plain_result(group_status_message)

    # ==================== 事件处理 ====================
    
    @filter.event_message_type(filter.EventMessageType.ALL, priority=1)
    async def handle_all_events(self, event: AstrMessageEvent):
        """统一事件处理入口 - 处理 .sunos 命令、自动回复和群事件"""
        try:
            # 优先处理 .sunos 命令（避免与其他功能冲突）
            incoming_message_text = event.message_str.strip()
            if incoming_message_text.startswith(".sunos"):
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