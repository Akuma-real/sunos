# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **SunKeyword intelligent keyword reply plugin** for AstrBot v2.0, providing **smart keyword auto-reply functionality**. The plugin has been completely simplified and optimized for dedicated keyword management with intelligent database migration.

## Development Commands

**Plugin Development Workflow**:
- Deploy to AstrBot plugins directory: `data/plugins/sunos/`
- Use VSCode to edit plugin files
- Reload plugin via AstrBot WebUI: Plugin Management → Manage → Reload Plugin
- Database auto-creates at `data/sunos/sunos_keywords.db`

**Code Formatting** (required before commits):
```bash
ruff format .  # Format code with ruff tool
```

**Test Commands**:
```bash
# Basic functionality  
/sunos ck list
/sunos ck add test "Test reply"  # Admin only
/sunos ck del 1                   # Admin only

# Note: /sunos help is handled by main SunOS plugin
```

## Smart Architecture v3.1

### Direct Implementation with Migration

**Single File Structure**:
```
main.py (Complete Plugin Implementation)
    ↓ (Intelligent Database Migration)
data/sunos/sunos_keywords.db (Optimized Keywords Database)
```

**Key Features**:
- **Smart Migration**: Automatic detection and migration from legacy database
- **Optimized Storage**: Standardized path structure following AstrBot best practices
- **Data Safety**: Backup creation during migration process
- **Backward Compatibility**: Seamless upgrade from v3.0 to v3.1

### Enhanced Database Management

**Optimized Table Design**:
```sql
CREATE TABLE keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    reply TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Migration Features**:
- **Automatic Detection**: Detects legacy database at startup
- **Safe Migration**: Creates backup before data transfer
- **Data Preservation**: Migrates only keyword data, ignoring deprecated tables
- **Error Recovery**: Cleanup on migration failure

### Core Functionality

**Keyword Management**:
- `_add_keyword()` - Insert with duplicate check
- `_delete_keyword()` - Delete by index
- `_list_keywords()` - Simple SELECT and format
- `_find_keyword_reply()` - Case-insensitive matching

**Command Processing**:
```python
@filter.command("sunos")
async def sunos_command(self, event):
    # Direct argument parsing
    # Simple if/elif command routing
    # Immediate database operations
```

**Auto Reply Logic**:
```python
@filter.event_message_type(filter.EventMessageType.ALL)
async def handle_auto_reply(self, event):
    # Skip commands
    # Direct keyword lookup
    # Immediate reply if match found
```

## Development Guidelines

### Simplicity Principles

**No Architecture Patterns**:
- ❌ No MVC, MVP, or complex patterns
- ❌ No service layers or repositories
- ❌ No dependency injection
- ✅ Direct implementation in main class

**Direct Database Access**:
```python
def _add_keyword(self, keyword: str, reply: str):
    with sqlite3.connect(self.db_path) as conn:
        # Direct SQL operations
        conn.execute("INSERT INTO keywords ...")
```

**Simple Error Handling**:
```python
try:
    # Database operation
except Exception as e:
    logger.error(f"Operation failed: {e}")
    return False, "Operation failed"
```

### Code Style

**Function Naming**:
- Use `_private_methods()` for internal operations
- Use descriptive names: `_add_keyword()` not `_add()`
- Keep methods focused and single-purpose

**Data Handling**:
- Use simple tuples for return values: `(success: bool, message: str)`
- Direct string formatting for user messages
- Basic validation without complex frameworks

**Event Handling**:
- Single event handler for auto-reply
- Skip command messages to avoid conflicts
- Direct string matching for keywords

### Testing Strategy

**Manual Testing**:
```bash
# Test keyword addition
/sunos ck add hello "Hello there!"

# Test auto-reply
# Send message containing "hello" 
# Should receive "Hello there!" as reply

# Test listing
/sunos ck list

# Test deletion
/sunos ck del 1
```

**Validation Points**:
- Admin permission checking works
- Keywords are case-insensitive matched
- Database operations complete successfully
- Auto-reply doesn't interfere with commands

## File Structure

**Simplified Structure**:
```
sunos/
├── main.py (Complete implementation ~230 lines)
└── CLAUDE.md (This documentation)
```

**What Was Removed**:
- ❌ `core/` directory with 8+ modules
- ❌ Complex service classes  
- ❌ Permission decorators
- ❌ Platform adapters
- ❌ Event handlers
- ❌ MVC architecture
- ❌ Dependency injection
- ❌ Test files and planning docs

## Core Features

**Available Commands**:
- `/sunos ck list` - List all keywords (anyone can use)
- `/sunos ck add <keyword> <reply>` - Add keyword (admin only)
- `/sunos ck del <index>` - Delete keyword by index (admin only)

**Note**: `/sunos help` and general SunOS commands are handled by the main SunOS controller plugin.

**Auto-Reply**:
- Scans all messages for keyword matches
- Case-insensitive substring matching
- Responds immediately with stored reply
- Skips command messages to avoid conflicts

**Administration**:
- Simple `event.role == "admin"` check
- No complex permission hierarchy
- No group-specific permissions

## Migration From v2.0

**What Changed**:
- Removed all MVC/service architecture
- Eliminated complex permission system
- Removed group management features
- Removed welcome message functionality  
- Removed blacklist management
- Removed platform adapter abstractions
- Simplified to pure keyword functionality

**Compatibility**:
- Database auto-migrates from legacy location
- Commands remain `/sunos ck ...` for compatibility with SunOS plugin series
- Auto-reply behavior unchanged
- Admin permission checking simplified

## Performance

**Database Operations**:
- **Smart Migration**: One-time migration from legacy database location
- **Optimized Path**: Follows AstrBot standard `data/sunos/` structure
- **Backup Safety**: Automatic backup creation during migration
- **Error Handling**: Comprehensive migration error recovery

**Memory Usage**:
- Single plugin class instance
- No complex object hierarchies
- Direct string processing
- Minimal memory footprint

**Processing Speed**:
- Direct method calls (no abstraction overhead)
- Simple string operations
- Fast SQLite queries
- Immediate response generation

This optimized version focuses on **intelligent keyword management** with **seamless database migration**, providing a **professional upgrade path** from the previous version while maintaining the core simplicity principle.