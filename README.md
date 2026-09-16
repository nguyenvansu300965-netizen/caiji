# 外贸客户采集软件

本地 Windows 桌面工具，用于从 Overture Maps、OpenStreetMap、授权 API 和用户指定的公开企业网页中提取公司名称、公开企业电话号码及来源。软件会标准化国际电话号码、标记移动号码、去重，并导出 Excel 或 CSV。

## 环境与启动

支持 Python 3.8+。在 PowerShell 中执行：

```powershell
python -m pip install -r requirements.txt
$env:GOOGLE_PLACES_API_KEY="你的 Google Places API 密钥"
$env:COLLECTOR_CONTACT_EMAIL="你的联系邮箱"
python -m src.main
```

打包版也可直接编辑程序同目录的 `config.json`：

```json
{
  "google_places_api_key": "你的 Google Places API 密钥",
  "contact_email": "你的联系邮箱"
}
```

保存后完全退出并重新启动软件。环境变量仍受支持，并且优先于配置文件。

数据库和日志默认保存在 `%LOCALAPPDATA%\TradeLeadCollector`。API 密钥只从进程环境变量读取，不写入数据库或日志。

## 数据源

- Overture Maps 官方开放数据：普通模式输入地区和英文关键词；国家批量模式会自动把国家拆分为空间网格，并运行外贸分类词包。首次运行会下载 DuckDB `httpfs` 扩展。
- OpenStreetMap / Overpass：填写国家、城市或地区，建议使用城市以避免公共实例超时；关键词可填写名称/行业词，或精确 OSM 标签（如 `industrial=machinery`）。程序会串行限速并处理 429。
- OpenStreetMap 国家 PBF：从 Geofabrik 下载可用的国家数据并通过 DuckDB Spatial 在本地查询，支持断点下载，适合补充大批量数据；文件可能达到数GB。
- Google Places 官方 API：在任务中填写行业/产品关键词和国家。需要在 Google Cloud 启用 Places API (New)，并配置 API 密钥、配额及账单。
- 公开企业网页：每行填写一个企业页面 URL。程序先检查 `robots.txt`，然后提取 JSON-LD 中的 Organization/LocalBusiness 电话或 `tel:` 链接。它不会自动绕过登录、验证码或访问限制。

Overture 数据需保留其数据来源要求；OpenStreetMap 数据遵循 ODbL 并需要署名。Google Places 内容通常禁止超出例外范围长期缓存，批量客户库应优先使用 Overture/OSM，使用 Google 数据前请核对最新服务条款。

仅处理有权访问的数据。B2B 平台优先使用官方 API 或授权导出；不要绕过登录、验证码、访问控制或平台明确的自动化禁令，也不要把私人手机号用于未经同意的营销。

## 十万级国家任务

1. 泛采集选择“多来源泛采集”，程序先运行 Overture 全国分片，再用 OpenStreetMap 补充；配置了 Google Places 密钥时还会运行多个通用企业查询。
2. 勾选“国家批量模式”并填写国家。需要最大数量时选择“全部”，软件采集所有带公开电话企业后再标记外贸相关性；也可选择严格、均衡或宽泛词包。
3. 设置目标数量；达到目标即停止，数据源不足时采集所有可用记录并生成缺口报告。
4. 任务按网格和分类保存检查点，程序重启后可继续；“查看覆盖报告”显示唯一客户、重复、无效、失败分片及目标缺口。
5. 客户数据每页显示500条；大批量建议导出 CSV，导出在后台执行。

“大宗商品”词包会在企业名称和 Overture 分类中合并检索金属矿产、石油天然气、煤炭、粮食糖棉、农产品、化工、塑料和橡胶，并按是否同时出现贸易/进出口/供应商特征评分。地图分类只能用于发现候选企业；确认真实进口采购行为仍需接入有授权的 HS 编码/海关贸易数据。

## 测试与打包

```powershell
python -m pytest
.\build.ps1
```

打包结果位于 `dist\外贸客户采集软件_v10.exe`。

## 使用限制

- 公开网页适配器只处理用户明确提供的页面，不做搜索引擎结果抓取。
- 10万是任务目标而不是数据源承诺；小国家或电话覆盖较低的国家可能无法达到，软件会报告实际可用数量。
- OSM 电话覆盖率取决于社区数据完整度，公共 Overpass 实例不适合大规模商业批处理。
- 电话类型依据 `phonenumbers` 元数据判断；公开企业地点中的移动号段会保留并标记为“移动号码”。这不代表号码一定属于企业负责人，也不代表人工确认可接通。
- Google Places 的可用字段、费用和分页行为以 Google 当前文档及账户配额为准。
