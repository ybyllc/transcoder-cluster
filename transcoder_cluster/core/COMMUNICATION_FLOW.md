# Transcoder Cluster 通信流程笔记

本文档说明主控端与子节点之间的通信流程、状态流转，以及近期“上传中 0%/节点 unknown”问题的原因与修复。

## 1. 组件与职责

- `Controller`（主控调度）  
  文件: `transcoder_cluster/core/controller.py`
- `Worker`（子节点 HTTP 服务）  
  文件: `transcoder_cluster/core/worker.py`
- `DiscoveryService`（主控发现节点）  
  文件: `transcoder_cluster/core/discovery.py`
- `HeartbeatService + DiscoveryResponder`（子节点广播状态/响应发现）  
  文件: `transcoder_cluster/core/discovery.py`
- `Controller GUI`（状态展示与操作入口）  
  文件: `gui/controller_app.py`

## 2. 通信协议概览

### 2.1 UDP（节点发现与心跳）

- 主控发送: `discovery` 广播
- 子节点响应: `discovery_response`（带 `hostname/ip/status`）
- 子节点周期发送: `heartbeat`（带 `status`）

说明:
- UDP 负责“有哪些节点、节点大致状态”。
- UDP 不负责转码结果传输。

### 2.2 HTTP（任务与结果）

Worker 端口默认 `9000`:

- `POST /task`  
  上传输入文件 + FFmpeg 参数，Worker 执行转码。
- `GET /status`  
  获取 Worker 实时状态（`receiving/processing/...` + `progress`）。
- `GET /download?file=...`  
  下载转码结果文件。
- `GET /capabilities`  
  获取 FFmpeg/编码器能力（含 NVENC 支持信息）。
- `GET /ping`  
  健康检查。

## 3. 主流程（自动分配模式）

### 3.1 节点发现阶段

1. 主控启动 `DiscoveryService`，广播 `discovery`。  
2. 子节点通过 `DiscoveryResponder` 回复 `discovery_response`。  
3. 子节点 `HeartbeatService` 周期发送 `heartbeat`。  
4. 主控维护 `discovered_nodes`，GUI 显示节点列表。

### 3.2 任务派发阶段

1. GUI 收集输入文件，调用 `Controller.create_tasks_for_files(...)` 生成任务列表。  
2. 调用 `Controller.dispatch_tasks(...)`。  
3. 调度策略: 每个节点并发 1 个任务；节点空闲后领取下一个任务；失败可重试。

### 3.3 单任务执行阶段

1. `Controller._submit_with_progress(...)` 启动一个轮询线程，每 0.5 秒请求 `GET /status`。  
2. 同时主线程调用 `submit_task(...)` 发送 `POST /task`。  
3. Worker 接收上传时更新:
   - `status = receiving`
   - `progress = 上传进度`
4. Worker 执行 FFmpeg 时更新:
   - `status = processing`
   - `progress = 转码进度`
5. 主控收到 `status` 后回调 GUI:
   - `receiving/uploading -> 任务状态“上传中”`
   - `processing -> 任务状态“处理中”`
6. 转码成功后主控调用 `download_result(...)` 拉取输出文件，并做输出文件有效性校验。

## 4. 状态流转

### 4.1 任务状态（主控 Task）

- `pending` -> `uploading` -> `processing` -> `completed`
- 异常分支: `failed/error`

### 4.2 节点状态（Worker.status）

- `idle`
- `receiving`（上传中）
- `processing`
- `completed`
- `error`
- `stopped`

## 5. 最近问题复盘（已修复）

### 5.1 现象

- 任务列表长期显示“上传中 0%”。
- 节点状态中“处理中”偶发变成 `unknown`。

### 5.2 根因

1. Worker 之前使用单线程 `HTTPServer`。  
   当 `POST /task` 长时间执行时，`GET /status` 易被阻塞/超时。  
2. GUI 端对轮询结果中瞬时 `unknown` 处理不够稳健，可能覆盖已有有效状态。
3. 主控轮询逻辑之前只把 `processing` 映射到任务进度，未把 `receiving` 映射为上传进度。

### 5.3 修复点

1. Worker 改为 `ThreadingHTTPServer`（`WorkerHTTPServer`），支持并发请求。  
2. `Controller._submit_with_progress(...)` 增加 `receiving/uploading` 状态处理。  
3. GUI 节点状态更新增加 `unknown` 覆盖保护，并在 `runtime_status=unknown` 时回退到发现通道状态。  
4. GUI 增加“上传中(%)”显示映射。

## 6. 排障建议

出现进度不更新时，按顺序检查:

1. Worker 是否可访问 `GET /status`（任务执行中仍可返回）。  
2. Worker `status` 是否包含 `status/progress`。  
3. 主控日志是否有持续 `获取 Worker 状态失败`。  
4. GUI 是否在持续收到 `on_node_update` 回调。  
5. 输出文件下载与校验是否通过（避免“看似完成但结果无效”）。

## 7. 后续可优化项

- 在 `POST /task` 上传阶段细分状态（如 `receiving_header/receiving_body`）。  
- 为 `/status` 增加时间戳字段，进一步提升状态新旧判断准确性。  
- 对网络抖动场景增加短窗口平滑，减少 UI 状态闪烁。
