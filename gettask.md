# 获取任务详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/v1/jobs/recordInfo:
    get:
      summary: 获取任务详情
      deprecated: false
      description: >-
        ## 概述


        使用此端点查询通过Market模型API创建的任何任务的状态和结果。这是一个统一的查询接口，适用于Market类别下的所有模型。


        ::: info[]

        此端点适用于所有Market模型，包括Seedream、Grok Imagine、Kling、Claude以及未来添加到Market的任何模型。

        :::


        ## 任务状态


        | 状态 | 描述 | 操作 |

        |-------|-------------|--------|

        | `waiting` | 任务已排队等待处理 | 继续轮询 |

        | `queuing` | 任务在处理队列中 | 继续轮询 |

        | `generating` | 任务正在处理中 | 继续轮询 |

        | `success` | 任务成功完成 | 解析`resultJson`获取结果 |

        | `fail` | 任务失败 | 查看`failCode`和`failMsg`了解详情 |


        ## 轮询最佳实践


        <AccordionGroup>

        <Accordion title="推荐的轮询间隔">
          - **初始轮询（前30秒）**: 每2-3秒
          - **30秒后**: 每5-10秒
          - **2分钟后**: 每15-30秒
          - **最大轮询时长**: 10-15分钟后停止并调查
          
        ::: tip[]
          使用指数退避来减少服务器负载和API成本。
        :::

        </Accordion>


        <Accordion title="使用回调而非轮询">
          对于生产应用，我们强烈建议在创建任务时使用`callBackUrl`参数：
          
          - **无需轮询**: 您的服务器自动接收通知
          - **降低API成本**: 消除持续的轮询请求
          - **更好的性能**: 任务完成时立即通知
          - **降低延迟**: 完成和通知之间无延迟
          
          查看各个模型文档了解回调实现详情。
        </Accordion>


        <Accordion title="处理已完成的任务">
          当`state`为`success`时：
          1. 将`resultJson`字符串解析为JSON
          2. 提取`resultUrls`数组
          3. 立即下载生成的内容
          4. 将内容存储在您自己的存储中
          
          **重要**: 生成的内容URL通常在24小时后过期。
        </Accordion>

        </AccordionGroup>


        ## 错误处理


        <ResponseExample>

        ```json 任务失败

        {
          "code": 200,
          "message": "success",
          "data": {
            "taskId": "task_12345678",
            "model": "grok-imagine/text-to-image",
            "state": "fail",
            "param": "{\"model\":\"grok-imagine/text-to-image\",\"input\":{\"prompt\":\"...\"}}",
            "resultJson": "",
            "failCode": "422",
            "failMsg": "Invalid prompt: prompt contains prohibited content",
            "completeTime": 1698765432000,
            "createTime": 1698765400000,
            "updateTime": 1698765432000
          }
        }

        ```

        </ResponseExample>


        ### 常见错误代码


        | 代码 | 描述 | 解决方案 |

        |------|-------------|----------|

        | `401` | 未授权 - API密钥无效或缺失 | 检查您的API密钥 |

        | `404` | 未找到任务 | 验证taskId是否正确 |

        | `422` | 原始请求中的验证错误 | 查看`failMsg`了解详情 |

        | `500` | 内部服务器错误 | 几分钟后重试 |

        | `501` | 生成失败 | 查看`failMsg`了解具体错误详情 |


        ## 示例: 完整的轮询流程


        ```javascript Node.js

        async function pollTaskStatus(taskId, maxAttempts = 60, interval = 5000)
        {
          for (let attempt = 0; attempt < maxAttempts; attempt++) {
            const response = await fetch(
              `https://api.kie.ai/api/v1/jobs/recordInfo?taskId=${taskId}`,
              {
                headers: { 'Authorization': 'Bearer YOUR_API_KEY' }
              }
            );
            
            const result = await response.json();
            const { state, resultJson, failMsg } = result.data;
            
            console.log(`尝试 ${attempt + 1}: 状态 = ${state}`);
            
            if (state === 'success') {
              const results = JSON.parse(resultJson);
              console.log('✅ 任务完成!');
              console.log('结果:', results.resultUrls);
              return results;
            }
            
            if (state === 'fail') {
              console.error('❌ 任务失败:', failMsg);
              throw new Error(failMsg);
            }
            
            // 仍在处理中，等待下次轮询
            await new Promise(resolve => setTimeout(resolve, interval));
          }
          
          throw new Error('任务在最大尝试次数后超时');
        }


        // 使用方法

        try {
          const results = await pollTaskStatus('task_12345678');
          console.log('生成的内容URL:', results.resultUrls);
        } catch (error) {
          console.error('错误:', error.message);
        }

        ```


        ## 速率限制


        - **最大查询速率**: 每个API密钥每秒10次请求

        - **推荐间隔**: 轮询之间间隔2-5秒


        ::: warning[]

        过度轮询可能导致速率限制。生产应用请使用回调。

        :::


        ## 相关资源


        <CardGroup cols={2}>
          <Card title="市场概览" icon="store" href="/cn/market/quickstart">
            探索所有可用模型
          </Card>
          <Card title="获取账户积分" icon="coins" href="/cn/common-api/get-account-credits">
            查看您的剩余积分
          </Card>
        </CardGroup>
      operationId: get-task-details
      tags:
        - docs/zh-CN/Market
      parameters:
        - name: taskId
          in: query
          description: 创建任务时返回的唯一任务标识符。
          required: true
          schema:
            type: string
            examples:
              - task_12345678
      responses:
        '200':
          description: 请求成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
                  - type: object
                    properties:
                      data:
                        type: object
                        description: 包含所有任务信息的数据对象
                        properties:
                          taskId:
                            type: string
                            description: 此任务的唯一标识符
                            examples:
                              - task_12345678
                          model:
                            type: string
                            description: >-
                              此任务使用的模型（例如
                              grok-imagine/text-to-image、seedream-4.0、kling-1.0）
                            examples:
                              - grok-imagine/text-to-image
                          state:
                            type: string
                            description: 任务的当前状态
                            enum:
                              - waiting
                              - queuing
                              - generating
                              - success
                              - fail
                            examples:
                              - success
                          param:
                            type: string
                            description: 包含创建任务时使用的原始请求参数的JSON字符串
                            examples:
                              - >-
                                {"model":"grok-imagine/text-to-image","callBackUrl":"https://your-domain.com/api/callback","input":{"prompt":"电影肖像...","aspect_ratio":"3:2"}}
                          resultJson:
                            type: string
                            examples:
                              - >-
                                {"resultUrls":["https://example.com/generated-content.jpg"]}
                            description: >-
                              包含生成的URL的JSON字符串。仅在状态为success时存在。根据outputMediaType的不同，结构为：图像/媒体/视频为{resultUrls:
                              []}，如果使用的是seedance 2以及seedance 2 fast
                              并且开启了return_last_frame,则返回的数据有{resultUrls:
                              [],firstFrameUrl:[],lastFrameUrl:[]},文本为{resultObject:
                              {}}
                          failCode:
                            type: string
                            description: 任务失败时的错误代码。成功时为空字符串
                            examples:
                              - ''
                          failMsg:
                            type: string
                            description: 任务失败时的错误消息。成功时为空字符串
                            examples:
                              - ''
                          costTime:
                            type: integer
                            format: int64
                            description: 处理时间（毫秒，成功时可用）
                            examples:
                              - 15000
                          completeTime:
                            type: integer
                            format: int64
                            description: 完成时间戳（Unix时间戳，毫秒）
                            examples:
                              - 1698765432000
                          createTime:
                            type: integer
                            format: int64
                            description: 创建时间戳（Unix时间戳，毫秒）
                            examples:
                              - 1698765400000
                          updateTime:
                            type: integer
                            format: int64
                            description: 最后更新时间戳（Unix时间戳，毫秒）
                            examples:
                              - 1698765432000
                          progress:
                            type: integer
                            description: 生成进度（0-100）。仅当模型为 sora2 或 sora2 pro 时返回。
                            minimum: 0
                            maximum: 100
                            examples:
                              - 45
                        x-apidog-orders:
                          - taskId
                          - model
                          - state
                          - param
                          - resultJson
                          - failCode
                          - failMsg
                          - costTime
                          - completeTime
                          - createTime
                          - updateTime
                          - progress
                        x-apidog-ignore-properties: []
                    x-apidog-orders:
                      - data
                    x-apidog-ignore-properties: []
              example:
                code: 200
                msg: success
                data:
                  taskId: task_12345678
                  model: grok-imagine/text-to-image
                  state: success
                  param: >-
                    {"model":"grok-imagine/text-to-image","callBackUrl":"https://your-domain.com/api/callback","input":{"prompt":"电影肖像...","aspect_ratio":"3:2"}}
                  resultJson: '{"resultUrls":["https://example.com/generated-content.jpg"]}'
                  failCode: ''
                  failMsg: ''
                  costTime: 15000
                  completeTime: 1698765432000
                  createTime: 1698765400000
                  updateTime: 1698765432000
          headers: {}
          x-apidog-name: ''
        '400':
          description: 错误的请求 - 缺少或无效的taskId参数
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:
                    type: integer
                  msg:
                    type: string
                required:
                  - code
                  - msg
                x-apidog-orders:
                  - code
                  - msg
                x-apidog-ignore-properties: []
              example:
                code: 400
                msg: taskId parameter is required
          headers: {}
          x-apidog-name: ''
        '401':
          description: 未授权 - API密钥无效或缺失
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:
                    type: integer
                  msg:
                    type: string
                required:
                  - code
                  - msg
                x-apidog-orders:
                  - code
                  - msg
                x-apidog-ignore-properties: []
              example:
                code: 401
                msg: Unauthorized
          headers: {}
          x-apidog-name: ''
        '404':
          description: 任务未找到 - 指定的taskId不存在
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:
                    type: integer
                  msg:
                    type: string
                required:
                  - code
                  - msg
                x-apidog-orders:
                  - code
                  - msg
                x-apidog-ignore-properties: []
              example:
                code: 404
                msg: Task not found
          headers: {}
          x-apidog-name: ''
        '429':
          description: 速率限制 - 请求过于频繁
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:
                    type: integer
                  msg:
                    type: string
                required:
                  - code
                  - msg
                x-apidog-orders:
                  - code
                  - msg
                x-apidog-ignore-properties: []
              example:
                code: 429
                msg: Rate limit exceeded
          headers: {}
          x-apidog-name: ''
        '500':
          description: 请求失败
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apidog-orders: []
                x-apidog-ignore-properties: []
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
      x-apidog-folder: docs/zh-CN/Market
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506624-run
components:
  schemas:
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          enum:
            - 200
            - 401
            - 402
            - 404
            - 422
            - 429
            - 455
            - 500
            - 501
            - 505
          description: |-
            响应状态码

            - **200**: 成功 - 请求已处理完成
            - **401**: 未授权 - 身份验证凭据缺失或无效
            - **402**: 积分不足 - 账户余额不足以执行该操作
            - **404**: 未找到 - 请求的资源或接口不存在
            - **422**: 参数验证错误 - 请求参数未通过校验
            - **429**: 调用频率超限 - 已超出该资源的请求限制
            - **455**: 服务不可用 - 系统正在维护中
            - **500**: 服务器内部错误 - 处理请求时发生意外故障
            - **501**: 生成失败 - 内容生成任务执行失败
            - **505**: 功能禁用 - 当前请求的功能已被禁用
        msg:
          type: string
          description: 响应消息，请求失败时返回错误描述
          examples:
            - success
        success:
          type: boolean
          description: 是否成功
      x-apidog-orders:
        - code
        - msg
        - success
      required:
        - success
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
# URL 文件上传

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/file-url-upload:
    post:
      summary: URL 文件上传
      deprecated: false
      description: |-
        :::info[]
          上传的文件为临时文件，3天后自动删除。
        :::

        ### 功能特点

        * 支持 HTTP 和 HTTPS 文件链接
        * 自动下载远程文件并上传
        * 自动从 URL 提取文件名或使用自定义文件名（相同文件名会覆盖旧文件，可能存在缓存延迟）
        * 自动识别 MIME 类型
        * 返回完整的文件信息和下载链接
        * API Key 认证保护
        * 上传文件为临时文件，3天后自动删除

        ### 支持的协议

        * **HTTP**：`http://example.com/file.jpg`
        * **HTTPS**：`https://example.com/file.jpg`

        ### 使用场景

        * 从其他服务迁移文件
        * 批量下载和存储网络资源
        * 备份远程文件
        * 缓存外部资源

        ### 重要说明

        * 确保提供的 URL 可公开访问
        * 下载超时时间为 30 秒
        * 推荐文件大小上限为 100MB
      operationId: upload-file-url
      tags:
        - docs/zh-CN/File Upload API
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UrlUploadRequest'
            examples:
              image_from_url:
                value:
                  fileUrl: https://example.com/images/sample.jpg
                  uploadPath: images/downloaded
                  fileName: my-downloaded-image.jpg
                summary: 从 URL 下载图片
              document_from_url:
                value:
                  fileUrl: https://example.com/docs/manual.pdf
                  uploadPath: documents/manuals
                summary: 从 URL 下载文档
      responses:
        '200':
          description: File uploaded successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                    description: Whether the request was successful
                  code:
                    type: integer
                    enum:
                      - 200
                      - 400
                      - 401
                      - 405
                      - 500
                    description: >-
                      Response Status Code


                      | Code | Description |

                      |------|-------------|

                      | 200 | Success - Request has been processed successfully
                      |

                      | 400 | Bad Request - Request parameters are incorrect or
                      missing required parameters |

                      | 401 | Unauthorized - Authentication credentials are
                      missing or invalid |

                      | 405 | Method Not Allowed - Request method is not
                      supported |

                      | 500 | Server Error - An unexpected error occurred while
                      processing the request |
                  msg:
                    type: string
                    description: Response message
                    examples:
                      - File uploaded successfully
                  data:
                    $ref: '#/components/schemas/FileUploadResult'
                required:
                  - success
                  - code
                  - msg
                  - data
                x-apidog-orders:
                  - success
                  - code
                  - msg
                  - data
                x-apidog-ignore-properties: []
              example:
                success: true
                code: 200
                msg: File uploaded successfully
                data:
                  fileName: uploaded-image.png
                  filePath: images/user-uploads/uploaded-image.png
                  downloadUrl: >-
                    https://tempfile.redpandaai.co/xxx/images/user-uploads/uploaded-image.png
                  fileSize: 154832
                  mimeType: image/png
                  uploadedAt: '2025-01-01T12:00:00.000Z'
          headers: {}
          x-apidog-name: SuccessResponse
        '400':
          description: Request parameter error
          content:
            application/json:
              schema: &ref_0
                $ref: '#/components/schemas/ApiResponse'
              examples:
                '2':
                  summary: missing_parameter
                  value:
                    success: false
                    code: 400
                    msg: 'Missing required parameter: uploadPath'
                '3':
                  summary: invalid_format
                  value:
                    success: false
                    code: 400
                    msg: 'Base64 decoding failed: Invalid Base64 format'
          headers: {}
          x-apidog-name: BadRequestError
        '401':
          description: Unauthorized access
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiResponse1'
              example:
                success: false
                code: 401
                msg: 'Authentication failed: Invalid API Key'
          headers: {}
          x-apidog-name: UnauthorizedError
        '500':
          description: Internal server error
          content:
            application/json:
              schema: *ref_0
              example:
                success: false
                code: 500
                msg: Internal server error
          headers: {}
          x-apidog-name: ServerError
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
      x-apidog-folder: docs/zh-CN/File Upload API
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506753-run
components:
  schemas:
    UrlUploadRequest:
      type: object
      properties:
        fileUrl:
          type: string
          format: uri
          description: 文件下载地址，必须为有效的 HTTP 或 HTTPS 地址
          examples:
            - https://example.com/images/sample.jpg
        uploadPath:
          type: string
          description: 文件上传路径，不带首尾斜杠
          examples:
            - images/downloaded
        fileName:
          type: string
          description: >-
            文件名（可选），包含文件扩展名。如不提供文件名，将自动生成随机文件名。若新上传的文件名与已存在文件名相同，则旧文件将被覆盖，但由于缓存原因，此更改可能不会立即生效
          examples:
            - sample-image.jpg
      required:
        - fileUrl
        - uploadPath
      x-apidog-orders:
        - fileUrl
        - uploadPath
        - fileName
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
    FileUploadResult:
      type: object
      properties:
        fileName:
          type: string
          description: File name
          examples:
            - uploaded-image.png
        filePath:
          type: string
          description: Complete file path in storage
          examples:
            - images/user-uploads/uploaded-image.png
        downloadUrl:
          type: string
          format: uri
          description: File download URL
          examples:
            - >-
              https://tempfile.redpandaai.co/xxx/images/user-uploads/uploaded-image.png
        fileSize:
          type: integer
          description: File size in bytes
          examples:
            - 154832
        mimeType:
          type: string
          description: File MIME type
          examples:
            - image/png
        uploadedAt:
          type: string
          format: date-time
          description: Upload timestamp
          examples:
            - '2025-01-01T12:00:00.000Z'
      required:
        - fileName
        - filePath
        - downloadUrl
        - fileSize
        - mimeType
        - uploadedAt
      x-apidog-orders:
        - fileName
        - filePath
        - downloadUrl
        - fileSize
        - mimeType
        - uploadedAt
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
    ApiResponse:
      type: object
      properties:
        success:
          type: boolean
          description: Whether the request was successful
        code:
          type: object
          properties: {}
        msg:
          type: string
          description: Response message
          examples:
            - File uploaded successfully
      required:
        - success
        - code
        - msg
      x-apidog-orders:
        - success
        - code
        - msg
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
    ApiResponse1:
      type: object
      properties:
        code:
          type: integer
          enum:
            - 200
            - 401
            - 402
            - 404
            - 422
            - 429
            - 455
            - 500
            - 501
            - 505
          description: |-
            响应状态码

            - **200**: 成功 - 请求已处理完成
            - **401**: 未授权 - 身份验证凭据缺失或无效
            - **402**: 积分不足 - 账户余额不足以执行该操作
            - **404**: 未找到 - 请求的资源或接口不存在
            - **422**: 参数验证错误 - 请求参数未通过校验
            - **429**: 调用频率超限 - 已超出该资源的请求限制
            - **455**: 服务不可用 - 系统正在维护中
            - **500**: 服务器内部错误 - 处理请求时发生意外故障
            - **501**: 生成失败 - 内容生成任务执行失败
            - **505**: 功能禁用 - 当前请求的功能已被禁用
        msg:
          type: string
          description: 响应消息，请求失败时返回错误描述
          examples:
            - success
        success:
          type: boolean
          description: 是否成功
      x-apidog-orders:
        - code
        - msg
        - success
      required:
        - success
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