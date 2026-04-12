# Grok Imagine 文生视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/v1/jobs/createTask:
    post:
      summary: Grok Imagine 文生视频
      deprecated: false
      description: >
        ## 查询任务状态


        提交任务后，使用统一的查询端点检查进度并获取结果：


        <Card title="获取任务详情" icon="lucide-search"
        href="/cn/market/common/get-task-detail">
          了解如何查询任务状态并获取生成结果
        </Card>


        ::: tip[]

        对于生产环境，我们建议使用 `callBackUrl` 参数接收自动通知，而不是轮询状态端点。

        :::


        ## 相关资源


        <CardGroup cols={2}>
          <Card title="市场概览" icon="lucide-store" href="/cn/market/quickstart">
            探索所有可用模型
          </Card>
          <Card title="通用API" icon="lucide-cog" href="/cn/common-api/get-account-credits">
            查看积分和账户使用情况
          </Card>
        </CardGroup>
      operationId: grok-imagine-text-to-video
      tags:
        - docs/zh-CN/Market/Video Models/Grok Imagine
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  description: |-
                    用于生成的模型名称。必填字段。

                    - 此端点必须使用 `grok-imagine/text-to-video`
                callBackUrl:
                  type: string
                  description: |-
                    接收视频生成任务完成更新的 URL。可选但建议在生产环境中使用。

                    - 当视频生成完成时，系统将向此 URL POST 任务状态和结果
                    - 回调包含生成的视频 URL 和任务信息
                    - 您的回调端点应接受包含视频结果的 JSON 负载的 POST 请求
                    - 或者，使用获取任务详情端点轮询任务状态
                input:
                  type: object
                  properties:
                    prompt:
                      type: string
                      description: |-
                        描述期望视频运动的文本提示。必填字段。

                        - 应该对期望的视觉运动详细具体
                        - 描述运动、动作序列、摄影工作和时间安排
                        - 包含主体、环境和运动动态的细节
                        - 最大长度：5000 字符
                        - 支持英文提示
                    aspect_ratio:
                      type: string
                      description: |-
                        指定生成视频的宽高比。控制输出的宽高比。

                        - **2:3**: 竖向（垂直）
                        - **3:2**: 横向（水平）
                        - **1:1**: 正方形
                        - **16:9**: 宽屏
                        - **9:16**: 竖屏

                        默认值：2:3
                    mode:
                      type: string
                      description: |-
                        指定影响运动风格和强度的生成模式。

                        - **fun**: 更有创意和趣味的解读
                        - **normal**: 平衡方法，具有良好的运动质量
                        - **spicy**: 更有活力和强烈的运动效果

                        默认值：normal
                    duration:
                      type: number
                      description: 生成的视频时长（秒）（6-30）。（最小值：6，最大值：30，步长：1）
                    resolution:
                      type: string
                      description: 生成视频的分辨率。
                      enum:
                        - 480p
                        - 720p
                      x-apidog-enum:
                        - value: 480p
                          name: ''
                          description: ''
                        - value: 720p
                          name: ''
                          description: ''
                      default: 480p
                      examples:
                        - 480p
                    nsfw_checker:
                      type: boolean
                      default: false
                      description: >-
                        默认值为 false。您可以根据需要将其设置为 false。如果设置为
                        false，我们的内容过滤功能将被禁用，所有结果将由模型直接返回。
                  required:
                    - prompt
                    - aspect_ratio
                    - mode
                    - resolution
                  x-apidog-orders:
                    - prompt
                    - aspect_ratio
                    - mode
                    - duration
                    - resolution
                    - nsfw_checker
                  description: 视频生成任务的输入参数
                  x-apidog-ignore-properties: []
              required:
                - model
                - callBackUrl
                - input
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: grok-imagine/text-to-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  A couple of doors open to the right one by one randomly and
                  stay open, to show the inside, each is either a living room,
                  or a kitchen, or a bedroom or an office, with little people
                  living inside.
                aspect_ratio: '2:3'
                mode: normal
                duration: '6'
                resolution: 480p
      responses:
        '200':
          description: 请求成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
              example:
                code: 200
                msg: success
                data:
                  taskId: 281e5b0*********************f39b9
          headers: {}
          x-apidog-name: ''
      security:
        - BearerAuth: []
          x-apidog:
            schemeGroups:
              - id: kn8M4YUlc5i0A0179ezwx
                schemeIds:
                  - BearerAuth
            required: true
            use:
              id: kn8M4YUlc5i0A0179ezwx
            scopes:
              kn8M4YUlc5i0A0179ezwx:
                BearerAuth: []
      x-apidog-folder: docs/zh-CN/Market/Video Models/Grok Imagine
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506656-run
components:
  schemas:
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          description: |-
            响应状态码
            200: 成功 - 请求已成功处理
            401: 未授权 - 缺少身份验证凭据或凭据无效
            402: 额度不足 - 账户额度不足，无法执行该操作
            404: 未找到 - 请求的资源或接口不存在
            422: 校验错误 - 请求参数未通过校验检查
            429: 请求受限 - 已超过该资源的请求频率限制
            455: 服务不可用 - 系统目前正在维护中
            500: 服务器错误 - 处理请求时发生了意外错误
            501: 生成失败 - 内容生成任务失败
            505: 功能禁用 - 请求的功能目前已禁用
        msg:
          type: string
          description: 响应消息，失败时的错误描述
        data:
          type: object
          properties:
            taskId:
              type: string
              description: 任务 ID 可与“获取任务详细信息”端点一起使用，以查询任务状态
          x-apidog-orders:
            - taskId
          required:
            - taskId
          x-apidog-ignore-properties: []
      x-apidog-orders:
        - code
        - msg
        - data
      required:
        - code
        - msg
        - data
      title: response not with recordId
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
  securitySchemes:
    BearerAuth:
      type: bearer
      scheme: bearer
      bearerFormat: API Key
      description: |-
        所有 API 都需要通过 Bearer Token 进行身份验证。

        获取 API Key：
        1. 访问 [API Key 管理页面](https://kie.ai/api-key) 获取您的 API Key

        使用方法：
        在请求头中添加：
        Authorization: Bearer YOUR_API_KEY

        注意事项：
        - 请妥善保管您的 API Key，切勿泄露给他人
        - 若怀疑 API Key 泄露，请立即在管理页面重置
servers:
  - url: https://api.kie.ai
    description: 正式环境
security:
  - BearerAuth: []
    x-apidog:
      schemeGroups:
        - id: kn8M4YUlc5i0A0179ezwx
          schemeIds:
            - BearerAuth
      required: true
      use:
        id: kn8M4YUlc5i0A0179ezwx
      scopes:
        kn8M4YUlc5i0A0179ezwx:
          BearerAuth: []

```
# Grok Imagine 图生视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/v1/jobs/createTask:
    post:
      summary: Grok Imagine 图生视频
      deprecated: false
      description: >
        ## 查询任务状态


        提交任务后，使用统一的查询端点检查进度并获取结果：


        <Card title="获取任务详情" icon="lucide-search"
        href="/cn/market/common/get-task-detail">
          了解如何查询任务状态并获取生成结果
        </Card>


        ::: tip[]

        对于生产环境，我们建议使用 `callBackUrl` 参数接收自动通知，而不是轮询状态端点。

        :::


        ## 相关资源


        <CardGroup cols={2}>
          <Card title="市场概览" icon="lucide-store" href="/cn/market/quickstart">
            探索所有可用模型
          </Card>
          <Card title="通用API" icon="lucide-cog" href="/cn/common-api/get-account-credits">
            查看积分和账户使用情况
          </Card>
        </CardGroup>
      operationId: grok-imagine-image-to-video
      tags:
        - docs/zh-CN/Market/Video Models/Grok Imagine
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  enum:
                    - grok-imagine/image-to-video
                  default: grok-imagine/image-to-video
                  description: |-
                    用于生成的模型名称。必填字段。

                    - 此端点必须使用 `grok-imagine/image-to-video`
                  examples:
                    - grok-imagine/image-to-video
                callBackUrl:
                  type: string
                  format: uri
                  description: |-
                    接收视频生成任务完成更新的 URL。可选但建议在生产环境中使用。

                    - 当视频生成完成时，系统将向此 URL POST 任务状态和结果
                    - 回调包含生成的视频 URL 和任务信息
                    - 您的回调端点应接受包含视频结果的 JSON 负载的 POST 请求
                    - 或者，使用获取任务详情端点轮询任务状态
                  examples:
                    - https://your-domain.com/api/callback
                input:
                  type: object
                  description: 视频生成任务的输入参数
                  properties:
                    image_urls:
                      type: array
                      items:
                        type: string
                        format: uri
                      description: >-
                        提供一个外部图像 URL 作为视频生成的参考。支持最多7个图像，不要与 task_id
                        同时使用。在提示词中引用已上传图片时，请输入 @image(n)，并在其后加一个空格（例如：@image1
                        海边日落）。


                        - 支持 JPEG、PNG、WEBP 格式

                        - 每张图像最大文件大小：10MB

                        - 使用外部图像时 Spicy 模式不可用

                        - 数组最多包含七个 URL
                      maxItems: 7
                      examples:
                        - - >-
                            https://file.aiquickdraw.com/custom-page/akr/section-images/1762247692373tw5di116.png
                    task_id:
                      type: string
                      description: >-
                        之前生成的 Grok 图像的任务 ID。与 index 配合使用选择特定图像，不要与 image_urls
                        同时使用。


                        - 使用 grok-imagine/text-to-image 生成的任务 ID

                        - 支持所有模式，包括 Spicy

                        - 最大长度：100 字符
                      maxLength: 100
                      examples:
                        - task_grok_12345678
                    index:
                      type: integer
                      description: |-
                        使用 task_id 时，指定使用哪个图像（Grok 每次生成 6 张图像）。仅与 task_id 配合使用。

                        - 基于 0 的索引 (0-5)
                        - 如果提供了 image_urls 则忽略此参数
                        - 默认值：0
                      minimum: 0
                      maximum: 5
                      default: 0
                      examples:
                        - 0
                    prompt:
                      type: string
                      description: |-
                        描述期望视频运动的文本提示。可选字段。

                        - 应该对期望的视觉运动详细具体
                        - 描述运动、动作序列、摄影工作和时间安排
                        - 包含主体、环境和运动动态的细节
                        - 最大长度：5000 字符
                        - 支持英文提示
                      examples:
                        - >-
                          POV hand comes into frame handing the girl a cup of
                          take away coffee, the girl steps out of the screen
                          looking tired, then takes it and she says happily:
                          "thanks! Back to work" she exits the frame and walks
                          right to a different part of the office.
                    mode:
                      type: string
                      description: |-
                        指定影响运动风格和强度的生成模式。注意：外部图像输入不支持 Spicy 模式。

                        - **fun**: 更有创意和趣味的解读
                        - **normal**: 平衡方法，具有良好的运动质量
                        - **spicy**: 更有活力和强烈的运动效果（外部图像不可用）

                        默认值：normal
                      enum:
                        - fun
                        - normal
                        - spicy
                      default: normal
                      examples:
                        - normal
                    duration:
                      type: number
                      description: 生成的视频时长（秒）（6-30）。（最小值：6，最大值：30，步长：1）
                    resolution:
                      type: string
                      description: 生成视频的分辨率。
                      enum:
                        - 480p
                        - 720p
                      x-apidog-enum:
                        - value: 480p
                          name: ''
                          description: ''
                        - value: 720p
                          name: ''
                          description: ''
                      default: 480p
                      examples:
                        - 480p
                    aspect_ratio:
                      type: string
                      description: 图像比例选择，仅适用于多图生成模式，单图模式下视频宽高参考图片宽高。
                      enum:
                        - '2:3'
                        - '3:2'
                        - '1:1'
                        - '16:9'
                        - '9:16'
                      x-apidog-enum:
                        - value: '2:3'
                          name: ''
                          description: ''
                        - value: '3:2'
                          name: ''
                          description: ''
                        - value: '1:1'
                          name: ''
                          description: ''
                        - value: '16:9'
                          name: ''
                          description: ''
                        - value: '9:16'
                          name: ''
                          description: ''
                      default: '16:9'
                    nsfw_checker:
                      type: boolean
                      default: false
                      description: >-
                        默认值为 false。您可以根据需要将其设置为 false。如果设置为
                        false，我们的内容过滤功能将被禁用，所有结果将由模型直接返回。
                  x-apidog-orders:
                    - image_urls
                    - task_id
                    - index
                    - prompt
                    - mode
                    - duration
                    - resolution
                    - aspect_ratio
                    - nsfw_checker
                  x-apidog-ignore-properties: []
              required:
                - model
                - input
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              examples:
                - model: grok-imagine/image-to-video
                  callBackUrl: https://your-domain.com/api/callback
                  input:
                    image_urls:
                      - >-
                        https://file.aiquickdraw.com/custom-page/akr/section-images/1762247692373tw5di116.png
                    prompt: >-
                      POV hand comes into frame handing the girl a cup of take
                      away coffee, the girl steps out of the screen looking
                      tired, then takes it and she says happily: "thanks! Back
                      to work" she exits the frame and walks right to a
                      different part of the office.
                    mode: normal
              x-apidog-ignore-properties: []
            example:
              model: grok-imagine/image-to-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                task_id: task_grok_12345678
                image_urls:
                  - >-
                    https://file.aiquickdraw.com/custom-page/akr/section-images/1762247692373tw5di116.png
                prompt: >-
                  POV hand comes into frame handing the girl a cup of take away
                  coffee, the girl steps out of the screen looking tired, then
                  takes it and she says happily: "thanks! Back to work" she
                  exits the frame and walks right to a different part of the
                  office.
                mode: normal
                duration: '6'
                resolution: 480p
                aspect_ratio: '16:9'
      responses:
        '200':
          description: 请求成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
              example:
                code: 200
                msg: success
                data:
                  taskId: 281e5b0*********************f39b9
          headers: {}
          x-apidog-name: ''
      security:
        - BearerAuth: []
          x-apidog:
            schemeGroups:
              - id: kn8M4YUlc5i0A0179ezwx
                schemeIds:
                  - BearerAuth
            required: true
            use:
              id: kn8M4YUlc5i0A0179ezwx
            scopes:
              kn8M4YUlc5i0A0179ezwx:
                BearerAuth: []
      x-apidog-folder: docs/zh-CN/Market/Video Models/Grok Imagine
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506657-run
components:
  schemas:
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          description: |-
            响应状态码
            200: 成功 - 请求已成功处理
            401: 未授权 - 缺少身份验证凭据或凭据无效
            402: 额度不足 - 账户额度不足，无法执行该操作
            404: 未找到 - 请求的资源或接口不存在
            422: 校验错误 - 请求参数未通过校验检查
            429: 请求受限 - 已超过该资源的请求频率限制
            455: 服务不可用 - 系统目前正在维护中
            500: 服务器错误 - 处理请求时发生了意外错误
            501: 生成失败 - 内容生成任务失败
            505: 功能禁用 - 请求的功能目前已禁用
        msg:
          type: string
          description: 响应消息，失败时的错误描述
        data:
          type: object
          properties:
            taskId:
              type: string
              description: 任务 ID 可与“获取任务详细信息”端点一起使用，以查询任务状态
          x-apidog-orders:
            - taskId
          required:
            - taskId
          x-apidog-ignore-properties: []
      x-apidog-orders:
        - code
        - msg
        - data
      required:
        - code
        - msg
        - data
      title: response not with recordId
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
  securitySchemes:
    BearerAuth:
      type: bearer
      scheme: bearer
      bearerFormat: API Key
      description: |-
        所有 API 都需要通过 Bearer Token 进行身份验证。

        获取 API Key：
        1. 访问 [API Key 管理页面](https://kie.ai/api-key) 获取您的 API Key

        使用方法：
        在请求头中添加：
        Authorization: Bearer YOUR_API_KEY

        注意事项：
        - 请妥善保管您的 API Key，切勿泄露给他人
        - 若怀疑 API Key 泄露，请立即在管理页面重置
servers:
  - url: https://api.kie.ai
    description: 正式环境
security:
  - BearerAuth: []
    x-apidog:
      schemeGroups:
        - id: kn8M4YUlc5i0A0179ezwx
          schemeIds:
            - BearerAuth
      required: true
      use:
        id: kn8M4YUlc5i0A0179ezwx
      scopes:
        kn8M4YUlc5i0A0179ezwx:
          BearerAuth: []

```
# 扩展 Grok Imagine 视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/v1/jobs/createTask:
    post:
      summary: 扩展 Grok Imagine 视频
      deprecated: false
      description: >
        ## 任务ID来源


        `task_id` 参数应从之前生成的视频任务中获取。您可以扩展使用以下方式创建的视频：


        <Card title="先生成视频" icon="lucide-video"
        href="/cn/market/grok-imagine/text-to-video">
          使用文本生成视频模型创建视频以获取可扩展的任务ID
        </Card>


        **如何获取任务ID：**

        1. 使用[文本生成视频API](/cn/market/grok-imagine/text-to-video)生成视频

        2. 从API响应中提取 `taskId`

        3. 将该 `taskId` 作为放大请求中的 `task_id` 参数使用


        ::: info[]

        只能扩展由Kie AI模型生成的视频。不支持外部视频。

        :::


        ## 查询任务状态


        提交扩展任务后，使用统一的查询端点检查进度并获取结果：


        <Card title="获取任务详情" icon="lucide-search"
        href="/cn/market/common/get-task-detail">
          了解如何查询任务状态并获取生成结果
        </Card>


        ::: tip[]

        对于生产环境，我们建议使用 `callBackUrl` 参数接收自动通知，而不是轮询状态端点。

        :::


        ## 相关资源


        <CardGroup cols={2}>
          <Card title="市场概览" icon="lucide-store" href="/cn/market/quickstart">
            探索所有可用模型
          </Card>
          <Card title="通用API" icon="lucide-cog" href="/cn/common-api/get-account-credits">
            查看积分和账户使用情况
          </Card>
        </CardGroup>
      operationId: grok-imagine-extend
      tags:
        - docs/zh-CN/Market/Video Models/Grok Imagine
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  description: |-
                    用于生成的模型名称。必填字段。

                    - 此端点必须使用 `grok-imagine/extend`
                  enum:
                    - grok-imagine/extend
                  default: grok-imagine/extend
                  x-apidog-enum:
                    - value: grok-imagine/extend
                      name: ''
                      description: ''
                  examples:
                    - grok-imagine/extend
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    接收视频扩展任务完成更新的 URL。可选但建议在生产环境中使用。


                    - 当视频扩展完成时，系统将向此 URL POST 任务状态和结果

                    - 回调包含生成的放大视频 URL 和任务信息

                    - 您的回调端点应接受包含视频结果的 JSON 负载的 POST 请求

                    - 或者，使用获取任务详情端点轮询任务状态

                    - 为确保回调安全性，请参阅 [Webhook
                    校验指南](/cn/common-api/webhook-verification) 了解签名验证实现方法
                  examples:
                    - 'https://your-domain.com/api/callback '
                input:
                  type: object
                  description: 视频扩展任务的输入参数
                  properties:
                    task_id:
                      type: string
                      description: |-
                        之前成功的视频生成任务的任务 ID。必填字段。

                        - 必须来自 Kie AI 视频生成模型（例如 grok-imagine/text-to-video）
                        - 原始图像生成必须成功完成
                        - 最大长度：100 字符
                        - 仅支持 Kie AI 生成的任务 ID
                      maxLength: 100
                      examples:
                        - task_grok_12345678
                    prompt:
                      type: string
                      description: |-
                        描述所需视频运动的文本提示。必填字段。

                        - 详细描述您希望视频如何扩展和延续
                        - 可以指定镜头运动、场景变化、物体动作等
                        - 提示词越具体，生成效果越符合预期
                        - 支持中英文输入
                      examples:
                        - 镜头缓慢推进，展示主角走进森林深处，阳光透过树叶洒下斑驳光影
                    extend_at:
                      type: number
                      description: 视频扩展的起点位置。选填字段.
                      examples:
                        - 0
                    extend_times:
                      type: string
                      enum:
                        - '6'
                        - '10'
                      x-apidog-enum:
                        - value: '6'
                          name: 6秒
                          description: 扩展6秒视频时长
                        - value: '10'
                          name: 10秒
                          description: 扩展10秒视频时长
                      default: '6'
                      examples:
                        - '6'
                      description: |-
                        视频扩展的持续时间（秒）。必填字段。

                        - `6`：扩展 6 秒视频内容
                        - `10`：扩展 10 秒视频内容
                        - 扩展时长越长，生成所需时间相应增加
                        - 根据场景复杂度选择合适的时长
                  required:
                    - task_id
                    - prompt
                    - extend_at
                    - extend_times
                  x-apidog-orders:
                    - task_id
                    - prompt
                    - extend_at
                    - extend_times
                  x-apidog-ignore-properties: []
              required:
                - model
                - input
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              examples:
                - model: grok-imagine/extend
                  callBackUrl: https://your-domain.com/api/callback
                  input:
                    task_id: task_grok_12345678
                    prompt: 镜头缓慢推进，展示主角走进森林深处，阳光透过树叶洒下斑驳光影
                    extend_at: 0
                    extend_times: '6'
              x-apidog-ignore-properties: []
            example:
              model: grok-imagine/extend
              callBackUrl: https://your-domain.com/api/callback
              input:
                task_id: task_grok_12345678
                prompt: ''
                extend_at: 0
                extend_times: '6'
      responses:
        '200':
          description: 请求成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
              example:
                code: 200
                msg: success
                data:
                  taskId: 281e5b0*********************f39b9
          headers: {}
          x-apidog-name: ''
      security:
        - BearerAuth: []
          x-apidog:
            schemeGroups:
              - id: kn8M4YUlc5i0A0179ezwx
                schemeIds:
                  - BearerAuth
            required: true
            use:
              id: kn8M4YUlc5i0A0179ezwx
            scopes:
              kn8M4YUlc5i0A0179ezwx:
                BearerAuth: []
      x-apidog-folder: docs/zh-CN/Market/Video Models/Grok Imagine
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-31340064-run
components:
  schemas:
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          description: |-
            响应状态码
            200: 成功 - 请求已成功处理
            401: 未授权 - 缺少身份验证凭据或凭据无效
            402: 额度不足 - 账户额度不足，无法执行该操作
            404: 未找到 - 请求的资源或接口不存在
            422: 校验错误 - 请求参数未通过校验检查
            429: 请求受限 - 已超过该资源的请求频率限制
            455: 服务不可用 - 系统目前正在维护中
            500: 服务器错误 - 处理请求时发生了意外错误
            501: 生成失败 - 内容生成任务失败
            505: 功能禁用 - 请求的功能目前已禁用
        msg:
          type: string
          description: 响应消息，失败时的错误描述
        data:
          type: object
          properties:
            taskId:
              type: string
              description: 任务 ID 可与“获取任务详细信息”端点一起使用，以查询任务状态
          x-apidog-orders:
            - taskId
          required:
            - taskId
          x-apidog-ignore-properties: []
      x-apidog-orders:
        - code
        - msg
        - data
      required:
        - code
        - msg
        - data
      title: response not with recordId
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
  securitySchemes:
    BearerAuth:
      type: bearer
      scheme: bearer
      bearerFormat: API Key
      description: |-
        所有 API 都需要通过 Bearer Token 进行身份验证。

        获取 API Key：
        1. 访问 [API Key 管理页面](https://kie.ai/api-key) 获取您的 API Key

        使用方法：
        在请求头中添加：
        Authorization: Bearer YOUR_API_KEY

        注意事项：
        - 请妥善保管您的 API Key，切勿泄露给他人
        - 若怀疑 API Key 泄露，请立即在管理页面重置
servers:
  - url: https://api.kie.ai
    description: 正式环境
security:
  - BearerAuth: []
    x-apidog:
      schemeGroups:
        - id: kn8M4YUlc5i0A0179ezwx
          schemeIds:
            - BearerAuth
      required: true
      use:
        id: kn8M4YUlc5i0A0179ezwx
      scopes:
        kn8M4YUlc5i0A0179ezwx:
          BearerAuth: []

```