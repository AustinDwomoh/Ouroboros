# Ouroboros Bot - Command Checklist & Issues

## ✅ Completed Commands
- [x] **break.py** - Working
- [x] **coinflip.py** - Working
- [x] **ouroboros.py** - Working
- [x] **rpsgame.py** - Working
- [x] **sporty.py** - Working
- [x] **embed.py** - Working
- [x] **leaderboard.py** - Working

## 🔧 In Progress / Needs Work

### rpsvs.py
**Status:** Broken
**Issue:** Winner determination error
```python
File "C:\Users\Inphinithy\Documents\projects\Ourobors-fixed\cmds\rpsvs.py", line 144, in handle_round
    result = await self.determine_winner(player1_choice, player2_choice)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```
**Priority:** High

### notifications.py
**Status:** Disabled
**Action:** Repurpose into something better
**Priority:** Low

### update.py
**Status:** Works but incomplete
**Action:** Make it do its intended purpose
**Priority:** Low

### channel_management
**Status:** Functional
**Action:** Connect help button to portfolio page for Ouroboros
**Priority:** Medium

### finance.py
**Status:** Needs improvement
**Issues:**
- Autocomplete functionality needs work
- Payment addition system needs improvement
**Priority:** Medium

### leveling.py
**Status:** Not started
**Action:** Start with first command
**Priority:** Medium

### movies.py
**Status:** Broken
**Action:** Fix the low-priority and easier issues first
**Priority:** High

## 🐛 Critical Bugs

### serverstat.py
**Issue:** Async/await not handled properly
```python
C:\Users\Inphinithy\Documents\projects\Ourobors-fixed\cogs\serverstat.py:112: 
RuntimeWarning: coroutine 'set_server_state' was never awaited
  ServerStatManager.set_server_state(guild_id, state)
```
**Additional Error:**
```python
C:\Users\Inphinithy\Documents\projects\Ourobors-fixed\Pc\Lib\site-packages\discord\ext\tasks\__init__.py:371: 
RuntimeWarning: coroutine 'get_server_state' was never awaited
  return await self.coro(*args, **kwargs)
```
**Fix Required:** Add `await` keywords to coroutine calls
**Priority:** Critical

### tournament.py
**Issues:**
1. Database issues
2. JSON serialization error
```python
discord.app_commands.errors.CommandInvokeError: Command 'activate_tournament' raised an exception: 
TypeError: Object of type coroutine is not JSON serializable
```
**Fix Required:** Await coroutines before JSON serialization
**Priority:** Critical

### welcome.py
**Issue:** Async/await not handled properly
```python
C:\Users\Inphinithy\Documents\projects\Ourobors-fixed\cogs\welcome.py:149: 
RuntimeWarning: coroutine 'set_channel_id' was never awaited
  ServerStatManager.set_channel_id(interaction.guild.id, "goodbye", channel.id)
```
**Fix Required:** Add `await` keyword
**Priority:** Critical

## 📋 Priority Order

### Critical (Fix Immediately)
1. **serverstat.py** - Unawaited coroutines
2. **tournament.py** - JSON serialization + coroutine issues
3. **welcome.py** - Unawaited coroutines

### High Priority
1. **movies.py** - Multiple issues (start with easier ones)
2. **rpsvs.py** - Winner determination broken

### Medium Priority
1. **channel_management** - Connect help to portfolio
2. **finance.py** - Improve autocomplete & payment system
3. **leveling.py** - Begin implementation

### Low Priority
1. **update.py** - Complete intended functionality
2. **notifications.py** - Repurpose feature

## 🔍 Common Pattern Detected

**Multiple files have unawaited coroutines!** 

Files affected:
- serverstat.py
- tournament.py
- welcome.py

**Solution:** Add `await` keyword before async function calls:
```python
# Wrong
ServerStatManager.set_server_state(guild_id, state)

# Correct
await ServerStatManager.set_server_state(guild_id, state)
```

## 📝 Notes
- Enable `tracemalloc` for better debugging of allocation tracebacks
- Consider implementing consistent error handling across all commands
- Document API changes and database schema