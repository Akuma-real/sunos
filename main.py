from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .database import SunosDatabase


@register(
    "sunos",
    "Akuma",
    "SunOS 群聊管理插件 - 词库管理、欢迎语、自动回复",
    "1.0.0",
    "https://github.com/Akuma-real/sunos",
)
class SunosPlugin(Star):
    # 权限级别常量
    PERMISSION_SUPER_ADMIN = "super_admin"  # AstrBot系统管理员
    PERMISSION_GROUP_ADMIN = "group_admin"  # 群聊管理员
    PERMISSION_USER = "user"  # 普通用户

    # 错误消息常量
    ADMIN_REQUIRED_MSG = "此操作需要管理员权限（系统管理员或群管理员）"
    SUPER_ADMIN_REQUIRED_MSG = "此操作需要系统管理员权限"
    GROUP_ONLY_MSG = "此功能仅支持群聊"
    INVALID_PARAMS_MSG = "参数错误，使用 /sunos help 查看帮助"

    # 帮助文本常量
    MAIN_HELP = """SunOS 群聊管理插件帮助

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

⚙️ 群聊开关:
/sunos enable - 开启功能 [管理员]
/sunos disable - 关闭功能 [管理员]
/sunos status - 查看状态（含权限信息）

权限说明:
[管理员] = 系统管理员 或 群聊管理员
占位符: {user} - @ 新成员, {group} - 群号"""

    def __init__(self, context: Context):
        super().__init__(context)
        self.db = SunosDatabase()
        # 群管理员信息缓存
        self._group_admin_cache = {}
        # 缓存时间戳
        self._cache_timestamps = {}
        # 缓存有效期（5分钟）
        self._cache_ttl = 300
        logger.info("SunOS 插件初始化完成")

    def _get_user_permission_level(self, event: AstrMessageEvent) -> str:
        """获取用户权限级别"""
        # 检查是否为AstrBot系统管理员
        if event.role == "admin":
            return self.PERMISSION_SUPER_ADMIN

        # 检查是否为群聊管理员
        group_id = event.get_group_id()
        if group_id and self._is_group_admin(event, group_id):
            return self.PERMISSION_GROUP_ADMIN

        return self.PERMISSION_USER

    def _is_group_admin(self, event: AstrMessageEvent, group_id: str) -> bool:
        """检查是否为群聊管理员"""
        try:
            user_id = event.get_sender_id()
            if not user_id:
                return False

            # 检查缓存
            cache_key = f"{group_id}_{user_id}"
            current_time = __import__('time').time()
            
            if (cache_key in self._group_admin_cache and 
                cache_key in self._cache_timestamps and
                current_time - self._cache_timestamps[cache_key] < self._cache_ttl):
                return self._group_admin_cache[cache_key]

            # 从平台元数据获取群管理员信息
            is_admin = False
            if hasattr(event, "platform_meta") and event.platform_meta:
                # 尝试从群成员信息中获取管理员列表
                group_admins = event.platform_meta.get("group_admins", [])
                owner_id = event.platform_meta.get("owner_id")

                # 检查是否为群主或管理员
                is_admin = str(user_id) == str(owner_id) or str(user_id) in [
                    str(admin_id) for admin_id in group_admins
                ]

            # 缓存结果
            self._group_admin_cache[cache_key] = is_admin
            self._cache_timestamps[cache_key] = current_time
            return is_admin

        except Exception as e:
            logger.error(f"检查群管理员权限失败: {e}")
            return False

    def _check_permission(
        self, event: AstrMessageEvent, required_level: str = None
    ) -> bool:
        """统一的权限检查方法

        Args:
            event: 消息事件
            required_level: 所需权限级别，None表示允许群管理员

        Returns:
            bool: 是否有权限
        """
        user_level = self._get_user_permission_level(event)

        if required_level == self.PERMISSION_SUPER_ADMIN:
            # 仅允许系统管理员
            return user_level == self.PERMISSION_SUPER_ADMIN
        else:
            # 允许系统管理员和群管理员
            return user_level in [
                self.PERMISSION_SUPER_ADMIN,
                self.PERMISSION_GROUP_ADMIN,
            ]

    def _check_admin_permission(self, event: AstrMessageEvent) -> bool:
        """检查是否有管理员权限（兼容性方法）"""
        return self._check_permission(event)

    def _check_group_chat(self, event: AstrMessageEvent) -> bool:
        """检查是否为群聊"""
        return event.get_group_id() is not None

    def _validate_params(self, params: list, min_count: int) -> bool:
        """验证参数数量"""
        return len(params) >= min_count

    @filter.command("sunos")
    async def sunos_main(self, event: AstrMessageEvent):
        """SunOS 群聊管理插件主命令"""
        try:
            # 解析命令参数
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

            # 群聊开关管理
            elif action in ["enable", "disable", "status"]:
                async for result in self._handle_group_commands(event, action):
                    yield result

            elif action == "help":
                yield event.plain_result(self.MAIN_HELP)

            else:
                yield event.plain_result("未知操作，使用 /sunos help 查看帮助")

        except Exception as e:
            logger.error(f"处理sunos命令失败: {e}")
            yield event.plain_result("命令处理失败，请稍后重试")

    async def _handle_keyword_commands(
        self, event: AstrMessageEvent, message_parts: list
    ):
        """处理词库管理命令"""
        if not self._validate_params(message_parts, 3):
            yield event.plain_result("用法: /sunos ck <add|del|list|help>")
            return

        subaction = message_parts[2]

        if subaction == "add":
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return
            if not self._validate_params(message_parts, 5):
                yield event.plain_result("用法: /sunos ck add <关键词> <回复内容>")
                return

            keyword = message_parts[3]
            reply = " ".join(message_parts[4:])
            reply = reply.replace("\\n", "\n")

            if self.db.add_keyword(keyword, reply):
                yield event.plain_result(
                    f"成功添加词库:\n关键词: {keyword}\n回复: {reply}"
                )
            else:
                yield event.plain_result(f"关键词 '{keyword}' 已存在！")

        elif subaction == "del":
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return
            if not self._validate_params(message_parts, 4):
                yield event.plain_result("用法: /sunos ck del <序号>")
                return

            try:
                index = int(message_parts[3])
            except ValueError:
                yield event.plain_result("序号必须是数字")
                return

            keywords = self.db.get_all_keywords()
            if not keywords:
                yield event.plain_result("当前没有词库条目")
                return

            if index < 1 or index > len(keywords):
                yield event.plain_result(
                    f"序号错误，请输入 1-{len(keywords)} 之间的数字"
                )
                return

            keyword_data = keywords[index - 1]
            if self.db.delete_keyword(keyword_data[0]):
                yield event.plain_result(f"成功删除词库: {keyword_data[1]}")
            else:
                yield event.plain_result("删除失败")

        elif subaction == "list":
            keywords = self.db.get_all_keywords()
            if not keywords:
                yield event.plain_result("当前没有词库条目")
                return

            result = f"📚 词库列表 (共 {len(keywords)} 条):\n\n"
            for i, (_, keyword, reply) in enumerate(keywords, 1):
                display_reply = reply[:50] + "..." if len(reply) > 50 else reply
                display_reply = display_reply.replace("\n", "\\n")
                result += f"{i}. {keyword} → {display_reply}\n"

            result += "\n使用 /sunos ck del <序号> 删除词库"
            yield event.plain_result(result)

        elif subaction == "help":
            help_text = """📚 词库管理帮助

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
            yield event.plain_result(help_text)
        else:
            yield event.plain_result("未知操作，使用 /sunos ck help 查看帮助")

    async def _handle_welcome_commands(
        self, event: AstrMessageEvent, message_parts: list
    ):
        """处理欢迎语管理命令"""
        if not self._validate_params(message_parts, 3):
            yield event.plain_result("用法: /sunos wc <set|del|show|help>")
            return

        subaction = message_parts[2]

        if subaction == "set":
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return
            if not self._validate_params(message_parts, 4):
                yield event.plain_result("用法: /sunos wc set <欢迎语内容>")
                return

            welcome_msg = " ".join(message_parts[3:])
            welcome_msg = welcome_msg.replace("\\n", "\n")
            group_id = event.get_group_id()

            if not group_id:
                yield event.plain_result(self.GROUP_ONLY_MSG)
                return

            if self.db.set_welcome_message(group_id, welcome_msg):
                yield event.plain_result(f"成功设置欢迎语:\n{welcome_msg}")
            else:
                yield event.plain_result("设置欢迎语失败")

        elif subaction == "del":
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return
            group_id = event.get_group_id()

            if not group_id:
                yield event.plain_result(self.GROUP_ONLY_MSG)
                return

            if self.db.delete_welcome_message(group_id):
                yield event.plain_result("成功删除当前群的欢迎语设置")
            else:
                yield event.plain_result("删除失败或当前群未设置欢迎语")

        elif subaction == "show":
            group_id = event.get_group_id()

            if not group_id:
                yield event.plain_result(self.GROUP_ONLY_MSG)
                return

            welcome_msg = self.db.get_welcome_message(group_id)
            if welcome_msg:
                yield event.plain_result(f"当前群欢迎语:\n{welcome_msg}")
            else:
                yield event.plain_result("当前群未设置欢迎语")

        elif subaction == "help":
            help_text = """👋 欢迎语管理帮助

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
            yield event.plain_result(help_text)
        else:
            yield event.plain_result("未知操作，使用 /sunos wc help 查看帮助")

    async def _handle_group_commands(self, event: AstrMessageEvent, action: str):
        """处理群聊开关命令"""
        if action in ["enable", "disable"]:
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return

            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result(self.GROUP_ONLY_MSG)
                return

            enabled = action == "enable"
            if self.db.set_group_enabled(group_id, enabled):
                status_msg = "✅ 已为当前群聊开启" if enabled else "❌ 已为当前群聊关闭"
                yield event.plain_result(f"{status_msg} SunOS 功能")
            else:
                yield event.plain_result("设置失败")

        elif action == "status":
            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result(self.GROUP_ONLY_MSG)
                return

            # 获取用户权限级别
            user_permission = self._get_user_permission_level(event)
            permission_text = {
                self.PERMISSION_SUPER_ADMIN: "🔒 系统管理员",
                self.PERMISSION_GROUP_ADMIN: "👑 群聊管理员",
                self.PERMISSION_USER: "👤 普通用户",
            }.get(user_permission, "❓ 未知权限")

            is_enabled = self.db.is_group_enabled(group_id)
            status = "✅ 已开启" if is_enabled else "❌ 已关闭"

            keywords_count = len(self.db.get_all_keywords())
            welcome_msg = self.db.get_welcome_message(group_id)
            has_welcome = "✅ 已设置" if welcome_msg else "❌ 未设置"

            result = f"""📊 SunOS 功能状态

群聊: {group_id}
功能状态: {status}
词库数量: {keywords_count} 条
欢迎语: {has_welcome}

👤 您的权限: {permission_text}"""

            yield event.plain_result(result)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_reply(self, event: AstrMessageEvent):
        """自动回复 - 精确匹配关键词并回复"""
        try:
            # 跳过指令消息和唤醒消息
            if event.is_at_or_wake_command:
                return

            group_id = event.get_group_id()

            # 检查群聊是否开启功能
            if group_id and not self.db.is_group_enabled(group_id):
                return

            # 精确匹配关键词（完全匹配消息内容）
            message_text = event.message_str.strip()
            keywords = self.db.get_all_keywords()

            for _, keyword, reply in keywords:
                if message_text == keyword:  # 精确匹配
                    yield event.plain_result(reply)
                    break  # 找到匹配后立即停止
        except Exception as e:
            logger.error(f"自动回复处理失败: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_events(self, event: AstrMessageEvent):
        """处理群聊事件 - 入群欢迎和退群通知"""
        try:
            # 跳过普通消息，只处理系统通知
            if event.message_str:  # 如果有文本消息内容，说明是普通消息
                return

            # 只处理群聊事件
            group_id = event.get_group_id()
            if not group_id:
                return

            # 检查群聊是否开启功能
            if not self.db.is_group_enabled(group_id):
                return

            # 获取原始消息数据
            raw_message = event.message_obj.raw_message
            logger.info(f"群事件原始数据: {raw_message}")

            # 处理不同类型的群事件
            # 方式1: 检查字典格式的原始消息
            if isinstance(raw_message, dict):
                notice_type = raw_message.get("notice_type")
                sub_type = raw_message.get("sub_type")
                user_id = raw_message.get("user_id")

                # 入群事件
                if notice_type == "group_increase" and user_id:
                    async for result in self._handle_member_join(
                        event, group_id, str(user_id)
                    ):
                        yield result
                # 退群事件
                elif notice_type == "group_decrease" and user_id:
                    async for result in self._handle_member_leave(
                        event,
                        group_id,
                        str(user_id),
                        str(sub_type) if sub_type else "unknown",
                    ):
                        yield result

            # 方式2: 检查对象属性格式
            elif hasattr(raw_message, "notice_type"):
                notice_type = getattr(raw_message, "notice_type", None)
                user_id = getattr(raw_message, "user_id", None)
                sub_type = getattr(raw_message, "sub_type", None)

                # 入群事件
                if notice_type == "group_increase" and user_id:
                    async for result in self._handle_member_join(
                        event, group_id, str(user_id)
                    ):
                        yield result
                # 退群事件
                elif notice_type == "group_decrease" and user_id:
                    async for result in self._handle_member_leave(
                        event,
                        group_id,
                        str(user_id),
                        str(sub_type) if sub_type else "unknown",
                    ):
                        yield result

        except Exception as e:
            logger.error(f"处理群事件失败: {e}")

    async def _handle_member_join(
        self, event: AstrMessageEvent, group_id: str, user_id: str
    ):
        """处理成员入群"""
        if not user_id:
            return

        welcome_msg = self.db.get_welcome_message(group_id)

        if welcome_msg:
            # 构建消息链，正确处理占位符
            import astrbot.api.message_components as Comp

            chain = []

            # 解析欢迎语，替换占位符
            parts = welcome_msg.split("{user}")
            for i, part in enumerate(parts):
                if i > 0:  # 在{user}位置添加At组件
                    chain.append(Comp.At(qq=user_id))
                if part:  # 添加文本部分
                    # 替换{group}占位符
                    text = part.replace("{group}", group_id)
                    chain.append(Comp.Plain(text))

            yield event.chain_result(chain)
        else:
            # 默认欢迎语，使用消息链
            import astrbot.api.message_components as Comp

            chain = [Comp.At(qq=user_id), Comp.Plain(" 欢迎加入群聊！")]
            yield event.chain_result(chain)

        logger.info(f"用户 {user_id} 加入了群聊 {group_id}")

    async def _handle_member_leave(
        self, event: AstrMessageEvent, group_id: str, user_id: str, sub_type: str
    ):
        """处理成员退群"""
        # 根据退群类型记录日志和发送通知
        if sub_type == "leave":
            logger.info(f"用户 {user_id} 主动离开了群聊 {group_id}")
            yield event.plain_result(f"用户 {user_id} 离开了群聊")
        elif sub_type == "kick":
            logger.info(f"用户 {user_id} 被踢出了群聊 {group_id}")
            yield event.plain_result(f"用户 {user_id} 被移出了群聊")
        elif sub_type == "kick_me":
            logger.info(f"机器人被踢出了群聊 {group_id}")
            # 机器人被踢出时无法发送消息
        else:
            logger.info(f"用户 {user_id} 离开了群聊 {group_id} (类型: {sub_type})")
            yield event.plain_result(f"用户 {user_id} 离开了群聊")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("SunOS 插件已卸载")
