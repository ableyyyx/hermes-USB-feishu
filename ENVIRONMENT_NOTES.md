# Environment & Dependency Notes

## Python Environment Setup

### Virtual Environment Location
```bash
# Hermes uses uv-managed virtual environment
source /home/kevin/tongyuan/hermes-USB-feishu/.venv/bin/activate
```

### Package Management
- **Package Manager**: `uv` (NOT pip)
- **Install packages**: `uv pip install <package>`
- **Why**: This is a uv-managed venv without pip installed

### Common Mistakes to Avoid

#### ❌ WRONG: Using pip directly
```bash
pip install qrcode[pil]              # Error: pip not found
python -m pip install qrcode[pil]    # Error: No module named pip
```

#### ✅ CORRECT: Using uv
```bash
uv pip install qrcode[pil]           # Works!
```

#### ❌ WRONG: Using system Python
```bash
python3 -m pip install qrcode[pil]   # Error: externally-managed-environment
pip3 install --user qrcode[pil]      # Error: externally-managed-environment
```

---

## Dashboard Startup

### Command
```bash
cd /home/kevin/tongyuan/hermes-USB-feishu
source .venv/bin/activate
hermes dashboard                      # NOT "hermes web"
```

### Common Mistakes

#### ❌ WRONG: Using "hermes web"
```bash
hermes web                           # Wrong command name
```

#### ✅ CORRECT: Using "hermes dashboard"
```bash
hermes dashboard                     # Correct command
```

---

## Frontend Build

### Build Command
```bash
cd /home/kevin/tongyuan/hermes-USB-feishu/web
npm run build
```

### Output Location
- Built files go to: `../hermes_cli/web_dist/`
- Dashboard serves from: `hermes_cli/web_dist/`

---

## Git Workflow

### Branch Structure
- Main branch: `main`
- Feature branches: `web-server`, `wechat-users`, etc.
- Current branch: `web-server`

### Commit Style
```bash
git commit -m "$(cat <<'EOF'
feat: Short title (imperative mood)

Detailed description of what changed and why.
Can be multiple paragraphs.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Common Dependencies

### Python Packages (in venv)
- `qrcode[pil]` - QR code generation (installed via uv)
- `fastapi` - Web framework
- `aiohttp` - Async HTTP client
- `uvicorn` - ASGI server

### System Packages
- Node.js & npm - Frontend build
- Git - Version control
- uv - Python package manager

---

## Troubleshooting

### Issue: "No module named 'qrcode'"
**Solution**: Install in venv using uv
```bash
uv pip install qrcode[pil]
```

### Issue: "pip: command not found" in venv
**Solution**: This is a uv-managed venv, use `uv pip` instead
```bash
uv pip install <package>
```

### Issue: "externally-managed-environment"
**Solution**: Don't use system pip, use venv
```bash
source .venv/bin/activate
uv pip install <package>
```

### Issue: Dashboard shows "会话已过期或不存在"
**Solution**: Check if QR poll endpoint is public
```python
# In web_server.py, ensure this is in auth_middleware:
if path.startswith("/api/wechat/qr-poll/"):
    return await call_next(request)
```

### Issue: Polling keeps running after dialog close
**Solution**: Use useRef to track and clear timeouts
```typescript
const pollTimeoutRef = useRef<number | null>(null);
// Clear on close:
if (pollTimeoutRef.current !== null) {
  clearTimeout(pollTimeoutRef.current);
}
```

---

## File Structure

### Key Directories
```
/home/kevin/tongyuan/hermes-USB-feishu/
├── .venv/                    # Virtual environment (uv-managed)
├── hermes_cli/
│   ├── web_server.py        # FastAPI backend
│   └── web_dist/            # Built frontend (from web/)
├── web/
│   ├── src/                 # React source
│   └── dist/                # Build output (→ web_dist/)
├── gateway/
│   └── platforms/
│       ├── weixin.py        # WeChat adapter
│       └── weixin_multi_user.py  # Multi-bot coordinator
└── tests/                   # Test suite
```

### Configuration Files
- `~/.hermes/config.yaml` - Operator config (shared)
- `~/.hermes/.env` - API keys (shared)
- `~/.hermes/user_profiles/wx_*/` - Per-bot profiles

---

## Testing

### Run Tests
```bash
source .venv/bin/activate
python -m pytest tests/ -q                        # Full suite
python -m pytest tests/test_hermes_constants.py   # Specific test
```

### Syntax Check
```bash
python3 -m py_compile hermes_cli/web_server.py
```

### Frontend Build Check
```bash
cd web && npm run build
```

---

## Security Notes

### Public API Endpoints
These endpoints do NOT require authentication:
- `/api/status`
- `/api/config/defaults`
- `/api/config/schema`
- `/api/model/info`
- `/api/dashboard/themes`
- `/api/dashboard/plugins`
- `/api/wechat/qr-poll/{session_id}` - For standalone QR page

### Protected Endpoints
All other `/api/*` endpoints require Bearer token authentication.

### Standalone Pages
- `/qr/{session_id}` - Public QR code page (no auth)
- All other routes - Require dashboard access

---

## Performance Notes

### QR Code Generation
- Backend generates QR as base64 PNG
- ~100-200ms per QR code
- Cached in session dict (in-memory)

### Polling Frequency
- Dashboard: 2 seconds
- Standalone page: 2 seconds
- Timeout: 8 minutes (480 seconds)

### Session Cleanup
- Sessions auto-expire after 8 minutes
- No automatic cleanup (TODO: add TTL cleanup)

---

## Known Issues & Workarounds

### Issue: Multiple polling loops after cancel
**Status**: ✅ FIXED (commit e5345370)
**Solution**: Use useRef to track and clear timeouts

### Issue: QR code shows ERR_CONNECTION_RESET
**Status**: ✅ FIXED (commit 42530770)
**Solution**: Generate QR as base64 image server-side

### Issue: 401 Unauthorized on QR poll
**Status**: ✅ FIXED (commit 33636e1d)
**Solution**: Add `/api/wechat/qr-poll/*` to public paths

---

## Future Improvements

1. **Session TTL Cleanup** - Auto-delete expired sessions from memory
2. **QR Code Refresh** - Auto-refresh expired QR codes
3. **Hot-Load** - Add bots without gateway restart
4. **Batch Operations** - Support batch bot deletion
5. **Internationalization** - Add English translations
