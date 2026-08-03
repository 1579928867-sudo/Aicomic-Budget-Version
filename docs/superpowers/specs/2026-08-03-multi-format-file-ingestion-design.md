# Multi-Format File Ingestion Design

**Date:** 2026-08-03
**Version:** v0.15
**Status:** Draft

## Overview

AI 漫剧当前只支持 `.txt` UTF-8 纯文本输入。本设计新增 `.docx` (Word) 和 `.pdf` (扫描版为主) 格式支持，通过一个轻量 `parsers/` 抽象层在入口处完成格式识别和文本提取，Orchestrator 及下游所有 agent 保持不变。

## Motivation

- 用户经常拿到 Word 和 PDF 格式的小说内容，每次需要手动转换为 txt 才能使用
- 扫描版 PDF 尤其常见（网文截图/扫描件），需要 OCR 才能提取文字
- 核心架构不变：摄入层和管线层天然解耦（Orchestrator 只收 `str`）

## Scope

**In scope:**
- `.txt` — 多编码自检测（utf-8 → gbk → gb18030）
- `.docx` — 段落文本提取（python-docx）
- `.pdf` — 双轨：pymupdf 嵌入文本层 → 不足则 Tesseract OCR
- `parsers/` 抽象层：协议 + 注册表 + 统一入口
- 配置项：PDF 解析阈值/DPI/语言

**Out of scope:**
- EPUB、HTML、Markdown（后续按需添加，parsers/ 结构天然支持扩展）
- PDF 表格/排版保留（用户确认不需要，纯文本提取即可）
- 云端 OCR（用户选择纯本地方案）
- `.doc`（旧版 Word）解析

## Architecture

```
CLI (main.py)
  │
  │  raw_text = parse_file(chapter_file)   ← 替代原先 read_text()
  ▼
parsers/__init__.py
  ├── detect_format(file_path) → str
  ├── parse_file(file_path) → str
  ├── PARSER_REGISTRY: list[FileParser]
  └── UnsupportedFormatError
  ▼
parsers/base.py           — FileParser 协议类
parsers/txt_parser.py     — UTF-8/GBK/GB18030 多编码
parsers/docx_parser.py    — python-docx 段落提取
parsers/pdf_parser.py     — pymupdf 文本提取 → Tesseract OCR 降级
  ▼
Orchestrator.run_chapter(chapter_id, raw_text)  ← 接口完全不变
```

### Key Design Decisions

1. **Orchestrator 零改动。** `raw_text` 始终是 `str`，来源对下游完全透明。
2. **Parser 协议 + 注册表。** 加新格式只需新增一个 parser 文件 + 在 `__init__.py` 注册一行。
3. **PDF 双轨自动降级。** pymupdf 先尝试提取嵌入文本；字符数低于阈值则自动走 OCR。对外统一为一个 `parse()` 调用。
4. **编码自检测。** txt parser 不再硬编码 UTF-8，按 `utf-8 → gbk → gb18030` 顺序尝试，覆盖中文网文常见编码。

## Components

### `base.py` — FileParser Protocol

```python
from typing import Protocol

class FileParser(Protocol):
    def parse(self, file_path: Path) -> str: ...

    @staticmethod
    def supports(file_path: Path) -> bool: ...
```

### `txt_parser.py`

| 项目 | 说明 |
|------|------|
| `supports()` | `.txt` 扩展名 |
| `parse()` | 依次尝试 utf-8, gbk, gb18030 编码读取，成功即返回 |
| 行数 | ~20 |

### `docx_parser.py`

| 项目 | 说明 |
|------|------|
| `supports()` | `.docx` 扩展名 |
| `parse()` | `Document(file_path)` → 遍历 `doc.paragraphs` → `p.text` → `\n\n` 拼接 |
| 忽略 | 图片、表格、页眉页脚（小说不依赖这些） |
| 行数 | ~25 |
| 依赖 | `python-docx>=1.0` |

### `pdf_parser.py`

| 项目 | 说明 |
|------|------|
| `supports()` | `.pdf` 扩展名 |
| `parse()` | 见下方流程图 |
| 行数 | ~60 |
| 依赖 | `pymupdf>=1.24`, `pytesseract>=0.3` |
| 系统依赖 | `tesseract-ocr` + `chi_sim` 语言包（首次手动安装） |

**PDF 解析流程：**

```
┌─────────────────┐
│ pymupdf.open()  │
└────────┬────────┘
         ▼
┌──────────────────────────┐
│ 遍历所有页面              │
│ page.get_text("text")    │
│ 所有页面文字拼接         │
└────────┬─────────────────┘
         ▼
    ┌────────────┐   YES   ┌──────────────────┐
    │ chars < 50? │────────▶│ Tesseract OCR    │
    └────────────┘         │ 逐页渲染 300dpi   │
         │ NO              │ pytesseract       │
         ▼                 │ lang=chi_sim+eng  │
  返回嵌入文本             └────────┬─────────┘
                                    ▼
                              返回 OCR 文本
```

### `__init__.py` — 统一入口

```python
PARSER_REGISTRY: list[FileParser] = [
    TxtParser(),
    DocxParser(),
    PdfParser(),
]

class UnsupportedFormatError(ValueError):
    """不支持的文件格式"""

def detect_format(file_path: Path) -> str:
    """返回检测到的格式名（日志/提示用）"""

def parse_file(file_path: Path) -> str:
    """
    统一解析入口。
    遍历 PARSER_REGISTRY，找到第一个 supports() 为 True 的 parser，
    调用其 parse() 返回纯文本。
    找不到则抛出 UnsupportedFormatError。
    """
```

## Configuration

`config/settings.yaml` 新增：

```yaml
parsers:
  pdf:
    min_text_chars: 50        # pymupdf 提取文字不足此值 → 判定扫描版，走 OCR
    ocr_dpi: 300              # 扫描版页面渲染分辨率
    ocr_langs: "chi_sim+eng"  # Tesseract 语言包
```

配置通过现有的 `config` 对象传入。`pdf_parser.py` 接受一个可选的 `PdfParserConfig` dataclass，未传入时使用上述默认值。

## Changes Required

### New Files

| File | Description |
|------|-------------|
| `src/aicomic/parsers/__init__.py` | Registry + `parse_file()` entry point |
| `src/aicomic/parsers/base.py` | `FileParser` protocol |
| `src/aicomic/parsers/txt_parser.py` | Multi-encoding text parser |
| `src/aicomic/parsers/docx_parser.py` | Word document parser |
| `src/aicomic/parsers/pdf_parser.py` | PDF parser with OCR fallback |

### Modified Files

| File | Change |
|------|--------|
| `src/aicomic/main.py` | L118: `read_text()` → `parse_file()`; L289: help text; add import |
| `pyproject.toml` | Add `python-docx`, `pymupdf`, `pytesseract` dependencies |
| `config/settings.yaml` | Add `parsers:` config block |

### Unchanged

- `src/aicomic/orchestrator.py` — 接口不变
- `src/aicomic/agents/*` — 全部不变
- `src/aicomic/db/*` — 全部不变
- `src/aicomic/llm/*` — 全部不变

## Error Handling

| 场景 | 行为 |
|------|------|
| 不支持的文件格式 | `UnsupportedFormatError`，含支持格式列表 |
| 文件不存在 | 保持现有 `FileNotFoundError` |
| DOCX 损坏/非 docx | `python-docx` 抛出 `ValueError`，包装为用户友好信息 |
| PDF 损坏 | `pymupdf` 抛出异常，包装后上抛 |
| Tesseract 未安装 | `pytesseract.TesseractNotFoundError`，附安装说明链接 |
| OCR 结果为空 | 警告日志 + 返回空字符串（让下游 empty check 报错） |

## Testing

- 每个 parser 独立单元测试：有效文件 → 期望文本；不支持的文件 → `supports()` 返回 False
- 集成测试：`parse_file()` 分别传入 `.txt`、`.docx`、`.pdf` → 返回非空 `str`
- PDF 扫描版模拟：用一个无嵌入文字层的 PDF 验证 OCR 路径触发
- 编码测试：GBK 编码的 txt 文件能正确解码

## Dependencies

### Python packages (added to pyproject.toml)

```
python-docx>=1.0       # Apache 2.0
pymupdf>=1.24          # AGPL — 独立工具模式不触发 copyleft，确认可接受
pytesseract>=0.3       # Apache 2.0
```

### System dependencies (用户手动安装)

```
tesseract-ocr           # Windows: https://github.com/UB-Mannheim/tesseract/wiki
  + chi_sim language pack
```

Tesseract 安装指引将在 README 中提供，也可通过 `aicomic --help-ocr` 查看。

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Tesseract 中文准确率不如预期 | 配置项 `ocr_langs` 支持用户调整；OCR 结果可人工复核 |
| 大 PDF（>100页）处理慢 | `min_text_chars` 阈值保证纯文本 PDF 不会误走 OCR；扫描版按需接受速度代价 |
| `pymupdf` AGPL 许可 | 非修改性使用（import 调用），不触发 copyleft |
| 编码检测 GBK/GB18030 误判 | 按顺序尝试，优先 UTF-8；误判仅影响乱码（不影响安全性），且 gb18030 是 gbk 超集 |

## Future Extensions (Out of Scope)

- EPUB parser — `ebooklib` 提取章节
- HTML parser — `BeautifulSoup` 提取正文
- Markdown parser — 保留标题层级作为场景分割提示
- 云端 OCR fallback — 百度/腾讯 OCR API 作为 Tesseract 的上层降级
