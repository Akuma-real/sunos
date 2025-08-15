import time
import threading
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
        # 缓存锁，确保线程安全
        self._cache_lock = threading.RLock()
        # 防刷屏机制：记录最近的通知时间
        self._last_notification_time = {}
        # 通知冷却时间（30秒）
        self._notification_cooldown = 30
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

            # 使用锁保护缓存操作，确保线程安全
            with self._cache_lock:
                # 检查缓存
                cache_key = f"{group_id}_{user_id}"
                current_time = time.time()

                if (
                    cache_key in self._group_admin_cache
                    and cache_key in self._cache_timestamps
                    and current_time - self._cache_timestamps[cache_key]
                    < self._cache_ttl
                ):
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

                # 缓存清理：移除过期条目（防止内存泄漏）
                self._cleanup_expired_cache(current_time)

                return is_admin

        except Exception as e:
            logger.error(f"检查群管理员权限失败: {e}")
            return False

    async def _is_bot_group_admin(self, event: AstrMessageEvent, group_id: str) -> bool:
        """检查机器人是否为群管理员

        Args:
            event: 消息事件
            group_id: 群组ID

        Returns:
            bool: 机器人是否为群管理员
        """
        try:
            platform_name = event.get_platform_name()
            if platform_name != "aiocqhttp":
                logger.warning(f"平台 {platform_name} 暂不支持检查机器人管理员权限")
                return False

            # 获取平台实例
            platform_mgr = self.context.platform_manager
            if not platform_mgr:
                return False

            platform_instance = None
            for platform in platform_mgr.platform_insts:
                if platform.metadata.name == "aiocqhttp":
                    platform_instance = platform
                    break

            if not platform_instance or not hasattr(platform_instance, "bot"):
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

    def _should_send_notification(self, notification_key: str) -> bool:
        """检查是否应该发送通知（防刷屏机制）

        Args:
            notification_key: 通知的唯一标识

        Returns:
            bool: 是否应该发送通知
        """
        current_time = time.time()
        last_time = self._last_notification_time.get(notification_key, 0)

        if current_time - last_time >= self._notification_cooldown:
            self._last_notification_time[notification_key] = current_time
            return True
        else:
            # 在冷却时间内，不发送通知
            logger.debug(f"通知 {notification_key} 在冷却时间内，跳过发送")
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

    def _validate_input_length(
        self, text: str, max_length: int = 1000, field_name: str = "输入"
    ) -> tuple[bool, str]:
        """验证输入长度，防止过长内容

        Args:
            text: 要验证的文本
            max_length: 最大长度限制
            field_name: 字段名称，用于错误提示

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

    # 黑名单管理核心方法
    def _add_user_to_blacklist(
        self, user_id: str, added_by: str, group_id: str = None, reason: str = ""
    ) -> tuple[bool, str]:
        """添加用户到黑名单

        Args:
            user_id: 要添加的用户ID
            added_by: 添加者的用户ID
            group_id: 群组ID，None表示全局黑名单
            reason: 添加原因

        Returns:
            tuple: (是否成功, 结果消息)
        """
        try:
            # 检查用户是否已在黑名单中
            if self.db.is_in_blacklist(user_id, group_id):
                scope_text = (
                    "全局黑名单" if group_id is None else f"群组 {group_id} 黑名单"
                )
                return False, f"用户 {user_id} 已在{scope_text}中"

            # 添加到黑名单
            if self.db.add_to_blacklist(user_id, added_by, group_id, reason):
                scope_text = "全局黑名单" if group_id is None else f"当前群组黑名单"
                reason_text = f"，原因：{reason}" if reason else ""
                return True, f"成功添加用户 {user_id} 到{scope_text}{reason_text}"
            else:
                return False, "添加黑名单失败，请稍后重试"

        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            return False, "添加黑名单失败，请稍后重试"

    def _remove_user_from_blacklist(
        self, user_id: str, group_id: str = None
    ) -> tuple[bool, str]:
        """从黑名单移除用户

        Args:
            user_id: 要移除的用户ID
            group_id: 群组ID，None表示全局黑名单

        Returns:
            tuple: (是否成功, 结果消息)
        """
        try:
            # 检查用户是否在黑名单中
            if not self.db.is_in_blacklist(user_id, group_id):
                scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
                return False, f"用户 {user_id} 不在{scope_text}中"

            # 从黑名单移除
            if self.db.remove_from_blacklist(user_id, group_id):
                scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
                return True, f"成功从{scope_text}移除用户 {user_id}"
            else:
                return False, "移除黑名单失败，请稍后重试"

        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            return False, "移除黑名单失败，请稍后重试"

    def _check_user_blacklist_status(
        self, user_id: str, group_id: str = None
    ) -> tuple[bool, str]:
        """检查用户黑名单状态

        Args:
            user_id: 用户ID
            group_id: 群组ID

        Returns:
            tuple: (是否在黑名单, 状态消息)
        """
        try:
            blacklist_info = self.db.get_user_blacklist_info(user_id, group_id)

            if blacklist_info:
                _, _, bl_group_id, reason, added_by, created_at = blacklist_info
                scope_text = (
                    "全局黑名单"
                    if bl_group_id is None
                    else f"群组 {bl_group_id} 黑名单"
                )
                reason_text = f"，原因：{reason}" if reason else ""
                return (
                    True,
                    f"用户 {user_id} 在{scope_text}中{reason_text}\n添加者：{added_by}\n添加时间：{created_at}",
                )
            else:
                return False, f"用户 {user_id} 不在黑名单中"

        except Exception as e:
            logger.error(f"检查黑名单状态失败: {e}")
            return False, "检查黑名单状态失败，请稍后重试"

    async def _kick_user_from_group(
        self, event: AstrMessageEvent, user_id: str, reason: str = ""
    ) -> tuple[bool, str]:
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

            # 获取平台名称，确保是支持踢人的平台
            platform_name = event.get_platform_name()
            if platform_name != "aiocqhttp":
                logger.warning(f"平台 {platform_name} 暂不支持自动踢人功能")
                return (
                    False,
                    f"当前平台 ({platform_name}) 暂不支持自动踢人功能{reason_text}",
                )

            # 检查机器人是否为群管理员
            is_bot_admin = await self._is_bot_group_admin(event, group_id)
            if not is_bot_admin:
                logger.warning(
                    f"机器人不是群 {group_id} 的管理员，无法踢出用户 {user_id}"
                )
                return (
                    False,
                    f"机器人无管理员权限，无法踢出用户{reason_text}",
                )

            try:
                # 通过 Context 获取平台管理器
                platform_mgr = self.context.platform_manager
                if not platform_mgr:
                    logger.warning("无法获取到平台管理器")
                    return (
                        False,
                        f"无法访问平台管理器{reason_text}，请联系管理员手动处理",
                    )

                # 获取当前平台实例
                platform_instance = None
                for platform in platform_mgr.platform_insts:
                    if platform.metadata.name == "aiocqhttp":
                        platform_instance = platform
                        break

                if not platform_instance or not hasattr(platform_instance, "bot"):
                    logger.warning("无法获取到 aiocqhttp 平台实例或 bot 对象")
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

            except Exception as api_error:
                logger.error(f"调用踢人API失败: {api_error}")
                return False, f"踢人操作失败{reason_text}，请联系管理员手动处理"

        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            return False, "踢出用户失败，请联系管理员手动处理"

    async def _scan_group_for_blacklist(
        self, event: AstrMessageEvent
    ) -> tuple[bool, str]:
        """扫描群内黑名单用户

        Args:
            event: 消息事件

        Returns:
            tuple: (是否成功, 结果消息)
        """
        try:
            group_id = event.get_group_id()
            if not group_id:
                return False, "此功能仅支持群聊"

            # 获取群成员列表
            group_members = await self._get_group_member_list(event, group_id)
            if not group_members:
                return False, "无法获取群成员列表，请稍后重试"

            logger.info(f"开始扫描群 {group_id}，共 {len(group_members)} 名成员")

            # 检查每个群成员是否在黑名单中
            found_users = []
            logger.info(f"开始检查 {len(group_members)} 名群成员的黑名单状态...")

            for i, user_id in enumerate(group_members):
                # 检查全局黑名单和群组黑名单
                is_blacklisted = self.db.is_in_blacklist(str(user_id), group_id)
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

            logger.info(
                f"在群 {group_id} 中发现 {len(found_users)} 个黑名单用户: {found_users}"
            )

            # 处理发现的黑名单用户
            kicked_count = 0
            failed_count = 0
            error_details = []

            for user_id in found_users:
                # 获取黑名单详情
                blacklist_info = self.db.get_user_blacklist_info(user_id, group_id)
                reason = ""
                if blacklist_info:
                    _, _, bl_group_id, bl_reason, added_by, created_at = blacklist_info
                    reason = bl_reason if bl_reason else "黑名单用户"
                    scope_text = "全局黑名单" if bl_group_id is None else "群组黑名单"
                    logger.info(
                        f"准备踢出用户 {user_id}，在{scope_text}中，原因：{reason}"
                    )

                success, msg = await self._kick_user_from_group(
                    event, user_id, f"黑名单用户：{reason}"
                )
                if success:
                    kicked_count += 1
                    logger.info(f"成功踢出黑名单用户 {user_id}")
                else:
                    failed_count += 1
                    error_details.append(f"用户 {user_id}: {msg}")
                    logger.warning(f"踢出黑名单用户 {user_id} 失败: {msg}")

            # 生成详细的结果报告
            result_msg = f"群内扫描完成，检查了 {len(group_members)} 名成员\n"
            result_msg += f"发现黑名单用户：{len(found_users)} 个\n"
            result_msg += f"成功处理：{kicked_count} 个\n"
            if failed_count > 0:
                result_msg += f"处理失败：{failed_count} 个\n"
                if error_details:
                    result_msg += "失败详情：\n" + "\n".join(
                        error_details[:3]
                    )  # 限制显示前3个错误
                    if len(error_details) > 3:
                        result_msg += f"\n... 还有 {len(error_details) - 3} 个错误"

            return True, result_msg

        except Exception as e:
            logger.error(f"扫描群内黑名单失败: {e}")
            return False, "扫描群内黑名单失败，请稍后重试"

    async def _get_group_member_list(
        self, event: AstrMessageEvent, group_id: str
    ) -> list:
        """获取群成员列表

        Args:
            event: 消息事件
            group_id: 群组ID

        Returns:
            list: 群成员ID列表
        """
        try:
            platform_name = event.get_platform_name()
            logger.info(f"获取群成员列表 - 平台: {platform_name}, 群组: {group_id}")

            if platform_name != "aiocqhttp":
                logger.warning(f"平台 {platform_name} 暂不支持获取群成员列表")
                return []

            # 通过 Context 获取平台管理器
            platform_mgr = self.context.platform_manager
            if not platform_mgr:
                logger.warning("无法获取到平台管理器")
                return []

            logger.info(
                f"平台管理器可用，共有 {len(platform_mgr.platform_insts)} 个平台实例"
            )

            # 获取当前平台实例
            platform_instance = None
            for platform in platform_mgr.platform_insts:
                logger.info(f"检查平台实例: {platform.metadata.name}")
                if platform.metadata.name == "aiocqhttp":
                    platform_instance = platform
                    break

            if not platform_instance:
                logger.warning("未找到 aiocqhttp 平台实例")
                return []

            if not hasattr(platform_instance, "bot"):
                logger.warning("aiocqhttp 平台实例没有 bot 对象")
                return []

            logger.info("正在调用 OneBot API 获取群成员列表...")

            # 调用 OneBot API 获取群成员列表
            response = await platform_instance.bot.call_action(
                "get_group_member_list", group_id=int(group_id)
            )

            logger.info(
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
                        logger.info(
                            f"成员 {i + 1}: {user_id} ({member.get('nickname', 'unknown')})"
                        )
                else:
                    logger.warning(f"成员数据格式异常: {member}")

            logger.info(f"成功获取群 {group_id} 成员列表，共 {len(member_ids)} 名成员")
            logger.info(f"成员ID列表: {member_ids}")
            return member_ids

        except Exception as e:
            logger.error(f"获取群成员列表失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

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

            # 黑名单管理
            elif action == "bl":
                async for result in self._handle_blacklist_commands(
                    event, message_parts
                ):
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

            # 输入验证
            keyword_valid, keyword_error = self._validate_input_length(
                keyword, 100, "关键词"
            )
            if not keyword_valid:
                yield event.plain_result(keyword_error)
                return

            reply_valid, reply_error = self._validate_input_length(
                reply, 1000, "回复内容"
            )
            if not reply_valid:
                yield event.plain_result(reply_error)
                return

            try:
                if self.db.add_keyword(keyword, reply):
                    yield event.plain_result(
                        f"成功添加词库:\n关键词: {keyword}\n回复: {reply}"
                    )
                else:
                    yield event.plain_result(f"关键词 '{keyword}' 已存在！")
            except Exception as e:
                logger.error(f"添加关键词失败: {e}")
                yield event.plain_result("添加词库失败，请稍后重试")

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

            # 输入验证
            msg_valid, msg_error = self._validate_input_length(
                welcome_msg, 500, "欢迎语"
            )
            if not msg_valid:
                yield event.plain_result(msg_error)
                return

            try:
                if self.db.set_welcome_message(group_id, welcome_msg):
                    yield event.plain_result(f"成功设置欢迎语:\n{welcome_msg}")
                else:
                    yield event.plain_result("设置欢迎语失败")
            except Exception as e:
                logger.error(f"设置欢迎语失败: {e}")
                yield event.plain_result("设置欢迎语失败，请稍后重试")

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

    async def _handle_blacklist_commands(
        self, event: AstrMessageEvent, message_parts: list
    ):
        """处理黑名单管理命令"""
        if not self._validate_params(message_parts, 3):
            yield event.plain_result("用法: /sunos bl <add|del|list|check|scan|help>")
            return

        subaction = message_parts[2]

        if subaction == "add":
            # 添加到黑名单
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return
            if not self._validate_params(message_parts, 4):
                yield event.plain_result("用法: /sunos bl add <user_id> [reason]")
                return

            user_id = message_parts[3]
            reason = " ".join(message_parts[4:]) if len(message_parts) > 4 else ""

            # 输入验证
            if not user_id.isdigit():
                yield event.plain_result("用户ID必须是数字")
                return

            reason_valid, reason_error = self._validate_input_length(
                reason, 200, "原因"
            )
            if not reason_valid:
                yield event.plain_result(reason_error)
                return

            # 获取群组ID和添加者ID
            group_id = event.get_group_id()
            added_by = event.get_sender_id()

            # 检查权限：全局黑名单需要系统管理员权限
            permission_level = self._get_user_permission_level(event)
            if group_id is None and permission_level != self.PERMISSION_SUPER_ADMIN:
                yield event.plain_result("添加全局黑名单需要系统管理员权限")
                return

            try:
                success, msg = self._add_user_to_blacklist(
                    user_id, added_by, group_id, reason
                )
                yield event.plain_result(msg)
            except Exception as e:
                logger.error(f"添加黑名单失败: {e}")
                yield event.plain_result("添加黑名单失败，请稍后重试")

        elif subaction == "del":
            # 从黑名单移除
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return
            if not self._validate_params(message_parts, 4):
                yield event.plain_result("用法: /sunos bl del <user_id>")
                return

            user_id = message_parts[3]

            if not user_id.isdigit():
                yield event.plain_result("用户ID必须是数字")
                return

            group_id = event.get_group_id()

            # 检查权限：全局黑名单需要系统管理员权限
            permission_level = self._get_user_permission_level(event)
            if group_id is None and permission_level != self.PERMISSION_SUPER_ADMIN:
                yield event.plain_result("操作全局黑名单需要系统管理员权限")
                return

            try:
                success, msg = self._remove_user_from_blacklist(user_id, group_id)
                yield event.plain_result(msg)
            except Exception as e:
                logger.error(f"移除黑名单失败: {e}")
                yield event.plain_result("移除黑名单失败，请稍后重试")

        elif subaction == "list":
            # 查看黑名单列表
            group_id = event.get_group_id()

            try:
                # 获取黑名单列表
                blacklist = self.db.get_blacklist(group_id, limit=20)  # 限制显示20条

                if not blacklist:
                    scope_text = "全局黑名单" if group_id is None else "当前群组黑名单"
                    yield event.plain_result(f"{scope_text}为空")
                    return

                scope_text = (
                    "全局黑名单" if group_id is None else f"群组 {group_id} 黑名单"
                )
                result = f"🚫 {scope_text} (显示前20条):\n\n"

                for i, (
                    _,
                    user_id,
                    bl_group_id,
                    reason,
                    added_by,
                    created_at,
                ) in enumerate(blacklist, 1):
                    reason_text = f" - {reason}" if reason else ""
                    scope_indicator = " [全局]" if bl_group_id is None else ""
                    result += f"{i}. {user_id}{scope_indicator}{reason_text}\n"

                result += f"\n总计：{len(blacklist)} 条记录"
                result += "\n使用 /sunos bl del <user_id> 移除用户"
                yield event.plain_result(result)

            except Exception as e:
                logger.error(f"获取黑名单列表失败: {e}")
                yield event.plain_result("获取黑名单列表失败，请稍后重试")

        elif subaction == "check":
            # 检查用户黑名单状态
            if not self._validate_params(message_parts, 4):
                yield event.plain_result("用法: /sunos bl check <user_id>")
                return

            user_id = message_parts[3]

            if not user_id.isdigit():
                yield event.plain_result("用户ID必须是数字")
                return

            group_id = event.get_group_id()

            try:
                is_blacklisted, status_msg = self._check_user_blacklist_status(
                    user_id, group_id
                )
                yield event.plain_result(status_msg)
            except Exception as e:
                logger.error(f"检查黑名单状态失败: {e}")
                yield event.plain_result("检查黑名单状态失败，请稍后重试")

        elif subaction == "scan":
            # 扫描群内黑名单用户
            if not self._check_admin_permission(event):
                yield event.plain_result(self.ADMIN_REQUIRED_MSG)
                return

            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result(self.GROUP_ONLY_MSG)
                return

            try:
                yield event.plain_result("正在扫描群内黑名单用户，请稍候...")
                success, result_msg = await self._scan_group_for_blacklist(event)
                yield event.plain_result(result_msg)
            except Exception as e:
                logger.error(f"扫描群内黑名单失败: {e}")
                yield event.plain_result("扫描群内黑名单失败，请稍后重试")

        elif subaction == "help":
            help_text = """🚫 黑名单管理帮助

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
            yield event.plain_result(help_text)
        else:
            yield event.plain_result("未知操作，使用 /sunos bl help 查看帮助")

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
            # 更精确的事件类型检测
            # 跳过普通文本消息和命令消息
            if (
                event.message_str
                and event.message_str.strip()
                and not self._is_system_notification(event)
            ):
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

    def _is_system_notification(self, event: AstrMessageEvent) -> bool:
        """判断是否为系统通知消息"""
        try:
            # 检查是否有原始消息数据
            if not hasattr(event, "message_obj") or not event.message_obj:
                return False

            raw_message = event.message_obj.raw_message

            # 检查是否包含系统事件类型
            if isinstance(raw_message, dict):
                return raw_message.get("notice_type") in [
                    "group_increase",
                    "group_decrease",
                    "group_admin",
                    "group_ban",
                ]
            elif hasattr(raw_message, "notice_type"):
                notice_type = getattr(raw_message, "notice_type", None)
                return notice_type in [
                    "group_increase",
                    "group_decrease",
                    "group_admin",
                    "group_ban",
                ]

            return False
        except Exception:
            return False

    async def _handle_member_join(
        self, event: AstrMessageEvent, group_id: str, user_id: str
    ):
        """处理成员入群"""
        if not user_id:
            return

        # 首先检查黑名单
        if self.db.is_in_blacklist(user_id, group_id):
            logger.info(f"检测到黑名单用户 {user_id} 尝试加入群聊 {group_id}")

            # 获取黑名单信息
            blacklist_info = self.db.get_user_blacklist_info(user_id, group_id)
            reason = ""
            if blacklist_info:
                _, _, bl_group_id, bl_reason, added_by, created_at = blacklist_info
                reason = bl_reason if bl_reason else "黑名单用户"
                scope_text = "全局黑名单" if bl_group_id is None else "群组黑名单"
                logger.info(
                    f"用户 {user_id} 在{scope_text}中，原因：{reason}，添加者：{added_by}"
                )

            # 尝试踢出用户
            success, kick_msg = await self._kick_user_from_group(
                event, user_id, f"黑名单用户：{reason}"
            )

            # 使用防刷屏机制，避免频繁通知
            notification_key = f"blacklist_join_{group_id}"
            should_notify = self._should_send_notification(notification_key)

            if success:
                # 发送踢出通知（如果不在冷却期）
                if should_notify:
                    import astrbot.api.message_components as Comp

                    chain = [
                        Comp.Plain(f"🚫 检测到黑名单用户 {user_id} 加入群聊\n"),
                        Comp.Plain(
                            f"已自动踢出，原因：{reason}" if reason else "已自动踢出"
                        ),
                    ]
                    yield event.chain_result(chain)
                logger.info(f"成功踢出黑名单用户 {user_id}")
            else:
                # 踢出失败，发送警告（如果不在冷却期）
                if should_notify:
                    import astrbot.api.message_components as Comp

                    chain = [
                        Comp.Plain(f"⚠️ 检测到黑名单用户 {user_id} 加入群聊\n"),
                        Comp.Plain(f"自动踢出失败，请管理员手动处理\n"),
                        Comp.Plain(f"失败原因：{kick_msg}\n"),
                        Comp.Plain(f"黑名单原因：{reason}" if reason else "黑名单用户"),
                    ]
                    yield event.chain_result(chain)
                logger.warning(f"踢出黑名单用户 {user_id} 失败: {kick_msg}")

            # 无论踢出是否成功，都不发送欢迎语
            return

        # 非黑名单用户，正常处理欢迎语
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
                # 替换{group}占位符并过滤空字符串
                if part:  # 只有非空部分才添加
                    text = part.replace("{group}", group_id)
                    if text.strip():  # 过滤空白文本，避免空Plain组件
                        chain.append(Comp.Plain(text))

            # 确保消息链不为空
            if not chain:
                chain = [Comp.At(qq=user_id), Comp.Plain(" 欢迎加入群聊！")]

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
        reason = ""
        notification_msg = ""

        if sub_type == "leave":
            reason = "主动退群"
            notification_msg = f"用户 {user_id} 离开了群聊"
            logger.info(f"用户 {user_id} 主动离开了群聊 {group_id}")
        elif sub_type == "kick":
            reason = "被踢出群"
            notification_msg = f"用户 {user_id} 被移出了群聊"
            logger.info(f"用户 {user_id} 被踢出了群聊 {group_id}")
        elif sub_type == "kick_me":
            logger.info(f"机器人被踢出了群聊 {group_id}")
            # 机器人被踢出时无法发送消息，直接返回
            return
        else:
            reason = f"离开群聊({sub_type})"
            notification_msg = f"用户 {user_id} 离开了群聊"
            logger.info(f"用户 {user_id} 离开了群聊 {group_id} (类型: {sub_type})")

        # 自动加入群黑名单
        if reason:  # 确保有原因记录
            try:
                # 检查用户是否已在黑名单中
                if not self.db.is_in_blacklist(user_id, group_id):
                    # 使用机器人ID作为添加者（因为是自动添加）
                    bot_id = "system_auto"  # 系统自动添加标识

                    success = self.db.add_to_blacklist(
                        user_id, bot_id, group_id, reason
                    )
                    if success:
                        logger.info(
                            f"已自动将用户 {user_id} 加入群 {group_id} 黑名单，原因：{reason}"
                        )
                        notification_msg += f"，已自动加入群黑名单"
                    else:
                        logger.warning(f"自动加入黑名单失败：用户 {user_id}")
                        notification_msg += f"，加入黑名单失败"
                else:
                    logger.info(
                        f"用户 {user_id} 已在群 {group_id} 黑名单中，跳过自动添加"
                    )
                    notification_msg += f"，已在群黑名单中"

            except Exception as e:
                logger.error(f"自动加入黑名单时发生错误: {e}")
                notification_msg += f"，加入黑名单时出错"

        # 使用防刷屏机制发送退群通知
        notification_key = f"member_leave_{group_id}"
        should_notify = self._should_send_notification(notification_key)

        if should_notify:
            yield event.plain_result(notification_msg)
        else:
            # 在冷却期内，只记录日志不发送通知
            logger.info(f"退群通知在冷却期内，跳过发送: {notification_msg}")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("SunOS 插件已卸载")
