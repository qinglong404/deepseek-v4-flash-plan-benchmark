# 隐私与安全边界

- 题库、代码和仓库均为合成夹具；没有加入测试者的真实项目源码。
- 原始请求包含模型提示和最终答案，用于复核评分，但不包含源代码中的 API key。
- 记录只保留 reasoning 字符数和 token 数；没有存储 reasoning 正文。
- 本机用户名路径已替换为相对路径或环境变量；实时采集必须显式提供 `MAGPIE_CONFIG` 或 `MAGPIE_BASE_URL` + `MAGPIE_API_KEY`。
- 没有打包 home 配置、SSH 密钥、浏览器数据、账号 ID、支付信息或账单导出。
- 请求和会话 UUID 是本地生成的随机标识，不用于登录或计费。
- 测试者报告的跨设备并发是人工观察，外部电脑的请求数、token 和重叠时间不在本仓库。

发布前检查会扫描常见私钥头、GitHub token 前缀、本机绝对路径和不应发布的配置文件。`scripts/validate_release.py` 可离线重复这些结构检查，但它不能替代仓库所有者对真实秘密轮换和账号权限的最终判断。

如果未来加入 live 采集，请使用专用网关凭据并限制权限。不要提交 `.env`、浏览器 cookie、OpenCode/Command Code 登录状态或任何厂商 API key。

