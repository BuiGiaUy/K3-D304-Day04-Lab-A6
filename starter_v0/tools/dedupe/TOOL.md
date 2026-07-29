---
name: dedupe
track: core
kind: local_formatter
provider: none
requires_env: []
inputs: [items, key, max_items]
outputs: [items, input_count, kept_count, removed_count]
side_effect: false
---
# dedupe

Tool mới do nhóm A6 viết.

Gộp danh sách item từ nhiều nguồn và bỏ các item trùng lặp, trả về danh sách sạch
để đưa tiếp vào `format`. Không gọi mạng, không cần API key.

`lookup`, `social_search` và `timeline` đều trả `items` cùng shape
(`title`, `url`, `source`, `summary`), nên khi một request cần nhiều nguồn thì kết
quả thường trùng nhau — cùng một bài báo xuất hiện ở cả web search lẫn tweet trích
dẫn lại. Tool này khử phần trùng đó trước bước trình bày.

## Cách so trùng

- `key="url"` (mặc định): so theo URL đã chuẩn hoá — bỏ query string và fragment,
  bỏ `www.`, bỏ `/` cuối, hạ chữ thường. Item không có URL thì lấy title thay.
- `key="title"`: so theo tiêu đề đã bỏ dấu tiếng Việt và hạ chữ thường
  (dùng `fold_text` trong `tools/_shared.py`).
- `key="both"`: chỉ coi là trùng khi cả URL lẫn title đều trùng.

Item xuất hiện trước được giữ lại; `max_items` cắt bớt phần đuôi.

## Lưu ý

`removed_count` chỉ đếm item bị loại vì trùng, không tính phần bị `max_items` cắt —
so `input_count` với `kept_count` để biết có bị cắt hay không.
