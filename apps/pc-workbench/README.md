# PC 工作台

PC 是独立学习实践场景、学习流采集端和本地分析中控台。学生显式开始任务后，
本机中枢才会采集前台窗口/进程事实；不采集屏幕、键盘、剪贴板或浏览历史。

启动本机中枢：

```powershell
cd C:\Users\Administrator\Desktop\知行智学\services\local-hub
.\scripts\run_pc_workbench.ps1
```

另开一个终端启动前端：

```powershell
cd C:\Users\Administrator\Desktop\知行智学\apps\pc-workbench
pnpm dev
```

前端代理到回环地址 `127.0.0.1:8777`。手机候选卡只能由学生明确关联到一个
PC 会话后显示，不会自动变成学习结论或 L1-L4 阶段。
