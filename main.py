"""SunKeyword 智能词库回复插件

专注于关键词自动回复功能的智能插件：
- 智能关键词匹配和回复
- 简单高效的管理界面
- 无复杂依赖的轻量级设计
"""

import sqlite3
import re
import os
import shutil
from typing import List, Tuple
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register(
    "sunkeyword",
    "Akuma",
    "SunKeyword 智能词库回复插件",
    "3.1.0",
    "https://github.com/Akuma-real/sunos-sunkeyword",
)
class SunKeywordPlugin(Star):
    """SunKeyword 智能词库回复插件 - 专注关键词自动回复"""

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

        # 新数据库路径配置（定位到 AstrBot 的 data 目录）
        # 插件路径: data/plugins/<plugin>/main.py -> 上溯三级到 data/
        self.base_data_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        data_dir = os.path.join(self.base_data_dir, "sunos")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "sunos_keywords.db")

        # 数据库迁移和初始化
        self._migrate_database()
        self._init_database()

        logger.info("SunKeyword 智能词库插件 v3.1.0 初始化完成")

    def _normalize_text(self, text: str) -> str:
        """将用户输入中的转义换行(\\n)转换为实际换行。"""
        try:
            return text.replace("\\n", "\n")
        except Exception:
            return text

    def _migrate_database(self):
        """数据库迁移：从旧路径迁移到新路径"""
        # 旧库位于 data/ 根目录下
        old_path = os.path.join(self.base_data_dir, "sunos_plugin.db")

        # 检查是否需要迁移
        if os.path.exists(old_path) and not os.path.exists(self.db_path):
            try:
                logger.info(f"检测到旧数据库，开始迁移：{old_path} -> {self.db_path}")

                # 创建备份
                backup_path = old_path + ".backup"
                shutil.copy2(old_path, backup_path)
                logger.info(f"已创建数据库备份：{backup_path}")

                # 迁移数据库（仅复制keywords表数据）
                self._migrate_keywords_data(old_path)

                logger.info("数据库迁移完成")

            except Exception as e:
                logger.error(f"数据库迁移失败: {e}")
                # 迁移失败时删除可能损坏的新数据库
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)

    def _migrate_keywords_data(self, old_path: str):
        """从旧数据库迁移关键词数据"""
        try:
            # 连接旧数据库
            with sqlite3.connect(old_path) as old_conn:
                # 获取关键词数据
                cursor = old_conn.execute(
                    "SELECT keyword, reply, created_at FROM keywords ORDER BY id"
                )
                keywords_data = cursor.fetchall()

            # 如果没有关键词数据，直接返回
            if not keywords_data:
                logger.info("旧数据库中没有关键词数据")
                return

            # 创建新数据库并插入数据
            with sqlite3.connect(self.db_path) as new_conn:
                # 创建关键词表
                new_conn.execute("""
                    CREATE TABLE IF NOT EXISTS keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        reply TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 插入关键词数据
                new_conn.executemany(
                    "INSERT INTO keywords (keyword, reply, created_at) VALUES (?, ?, ?)",
                    keywords_data,
                )
                new_conn.commit()

                logger.info(f"成功迁移 {len(keywords_data)} 条关键词数据")

        except Exception as e:
            logger.error(f"关键词数据迁移失败: {e}")
            raise

    def _init_database(self):
        """初始化数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        reply TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("SunKeyword 数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查是否为管理员"""
        return event.is_admin()

    def _add_keyword(self, keyword: str, reply: str) -> Tuple[bool, str]:
        """添加关键词"""
        try:
            # 规范化换行：将“\n”转为实际换行
            reply = self._normalize_text(reply)
            with sqlite3.connect(self.db_path) as conn:
                # 检查是否已存在
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM keywords WHERE keyword = ?", (keyword,)
                )
                if cursor.fetchone()[0] > 0:
                    return False, f"关键词 '{keyword}' 已存在"

                # 添加新关键词
                conn.execute(
                    "INSERT INTO keywords (keyword, reply) VALUES (?, ?)",
                    (keyword, reply),
                )
                conn.commit()
                return True, f"成功添加关键词 '{keyword}'"
        except Exception as e:
            logger.error(f"添加关键词失败: {e}")
            return False, "添加关键词失败"

    def _delete_keyword(self, index: int) -> Tuple[bool, str]:
        """删除关键词"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 获取所有关键词
                cursor = conn.execute("SELECT id, keyword FROM keywords ORDER BY id")
                keywords = cursor.fetchall()

                if index < 1 or index > len(keywords):
                    return False, f"序号无效，请输入 1-{len(keywords)} 之间的数字"

                # 删除指定关键词
                keyword_id, keyword = keywords[index - 1]
                conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
                conn.commit()
                return True, f"成功删除关键词 '{keyword}'"
        except Exception as e:
            logger.error(f"删除关键词失败: {e}")
            return False, "删除关键词失败"

    def _list_keywords(self) -> str:
        """列出所有关键词"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT keyword, reply FROM keywords ORDER BY id")
                keywords = cursor.fetchall()

                if not keywords:
                    return "当前没有词库记录"

                lines = ["📚 当前词库列表:", ""]
                for i, (keyword, reply) in enumerate(keywords, 1):
                    # 限制显示长度
                    normalized = self._normalize_text(reply)
                    reply_preview = (
                        normalized[:30] + "..." if len(normalized) > 30 else normalized
                    )
                    lines.append(f"{i}. {keyword} → {reply_preview}")

                lines.append(f"\n共 {len(keywords)} 条记录")
                # 使用实际换行符拼接
                return "\n".join(lines).replace("\\n", "\n")
        except Exception as e:
            logger.error(f"获取词库列表失败: {e}")
            return "获取词库列表失败"

    def _find_keyword_reply(self, message: str) -> str:
        """查找关键词回复（严格相等匹配）

        规则：
        - 全部关键词均使用严格相等匹配（区分大小写，保留空格与符号）
        - 不进行大小写转换或首尾空格裁剪
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT keyword, reply FROM keywords")
                keywords = cursor.fetchall()

                for keyword, reply in keywords:
                    kw = str(keyword)
                    # 忽略字母大小写进行严格相等比较（空格/符号保持严格）
                    if kw.casefold() == message.casefold():
                        return reply

                return None
        except Exception as e:
            logger.error(f"关键词匹配失败: {e}")
            return None

    # ==================== 命令处理 ====================

    @filter.command("sunos")
    async def sunos_command(self, event: AstrMessageEvent):
        """处理 /sunos 命令"""
        args = event.message_str.strip().split()

        if len(args) < 2:
            return  # 不处理，交给主控插件处理

        if args[1] == "ck":
            async for result in self._handle_keyword_commands(event, args):
                yield result
        # 移除help处理，交给主控插件

    @filter.command_group("sunos")
    async def sunos_dot_command(self, event: AstrMessageEvent):
        """处理 .sunos 命令"""
        args = event.message_str.strip().split()

        if len(args) < 2:
            return  # 不处理，交给主控插件处理

        if args[1] == "ck":
            async for result in self._handle_keyword_commands(event, args):
                yield result
        # 移除help处理，交给主控插件

    async def _handle_keyword_commands(self, event: AstrMessageEvent, args: List[str]):
        """处理词库子命令"""
        if len(args) < 3:
            yield event.plain_result("用法: /sunos ck <help|add|del|list>")
            return

        sub_cmd = args[2]

        if sub_cmd in ("help", "h", "?"):
            yield event.plain_result(
                "SunKeyword 指南:\n".replace("\\n", "\n")
                + "- /sunos ck list         查看当前词库\n".replace("\\n", "\n")
                + "- /sunos ck add 词 回复  添加词库（管理员）\n".replace("\\n", "\n")
                + "- /sunos ck del 序号     删除词库（管理员）\n".replace("\\n", "\n")
                + "提示: 也支持以 .sunos 为前缀，例如 .sunos ck list"
            )
            return

        if sub_cmd == "add":
            if not self._is_admin(event):
                yield event.plain_result("此操作需要管理员权限")
                return

            # 使用正则保留换行：匹配 '.sunos ck add <关键词> <回复...>' 或 '/sunos ...'
            raw = event.message_str
            m = re.match(r"^[\./]sunos\s+ck\s+add\s+(\S+)\s+([\s\S]+)$", raw)
            if m:
                keyword = m.group(1)
                reply = m.group(2)
            else:
                # 回退到原有解析（不保留换行）
                if len(args) < 5:
                    yield event.plain_result("用法: /sunos ck add <关键词> <回复内容>")
                    return
                keyword = args[3]
                reply = " ".join(args[4:])
            success, message = self._add_keyword(keyword, reply)
            yield event.plain_result(message)

        elif sub_cmd == "del":
            if not self._is_admin(event):
                yield event.plain_result("此操作需要管理员权限")
                return

            if len(args) < 4:
                yield event.plain_result("用法: /sunos ck del <序号>")
                return

            try:
                index = int(args[3])
                success, message = self._delete_keyword(index)
                yield event.plain_result(message)
            except ValueError:
                yield event.plain_result("序号必须是数字")

        elif sub_cmd == "list":
            message = self._list_keywords()
            yield event.plain_result(message)

        else:
            yield event.plain_result("未知操作，使用 /sunos ck help 查看帮助")

    # ==================== 自动回复 ====================

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1)
    async def handle_auto_reply(
        self, event: AstrMessageEvent, context: Context = None, *args, **kwargs
    ):
        """处理自动回复"""
        try:
            raw_text = event.message_str
            trimmed = raw_text.strip()

            # 跳过命令消息
            if trimmed.startswith(("/sunos", ".sunos")):
                return
            # 尝试跳过由本插件产生的提示类消息，避免自触发
            if any(
                flag in trimmed
                for flag in (
                    "成功添加关键词",
                    "成功删除关键词",
                    "📚 当前词库列表",
                )
            ):
                return

            # 查找匹配的关键词
            reply = self._find_keyword_reply(raw_text)
            if reply:
                # 输出前规范化：处理用户存储的“\n”
                yield event.plain_result(self._normalize_text(reply))

        except Exception as e:
            logger.error(f"自动回复失败: {e}")

    async def terminate(self):
        """插件卸载"""
        logger.info("SunKeyword 智能词库插件 v3.1.0 已卸载")
