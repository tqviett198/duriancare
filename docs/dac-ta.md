# ĐẶC TẢ CHI TIẾT HỆ THỐNG: SỔ VƯỜN SẦU RIÊNG (DurianCare)

**Phiên bản:** 1.0 (Bản đặc tả đầy đủ hợp nhất)  
**Stack kỹ thuật:** Python 3.12 · Django 5.2 & Django REST Framework · PostgreSQL / SQLite · React (Responsive & PWA) · Celery 5.6 + Redis · Docker Compose  
**Tiêu chuẩn chất lượng:** VietGAP · GlobalGAP · Tiêu chuẩn xuất khẩu chính ngạch (Nghị định thư Việt Nam - Trung Quốc & EU)  

---

## 1. Ma trận phân quyền người dùng (Role-Based Access Control)

Hệ thống quản lý vườn theo mô hình đa vườn (multi-farm), phạm vi URL chuẩn: `/api/v1/farms/{farm_id}/...`. Mỗi tài khoản có vai trò xác định trên từng vườn thông qua `FarmMembership`:

| Chức năng | OWNER (Chủ vườn) | WORKER (Người làm vườn) | ADVISOR (Kỹ thuật viên / HTX) |
|---|:---:|:---:|:---:|
| **Quản trị vườn, thành viên, lô đất, mã vùng trồng** | Toàn quyền | Chỉ xem | Chỉ xem |
| **Ghi nhật ký canh tác (FarmLog)** | Xem / Tạo / Hủy | Xem / Tạo | Chỉ xem |
| **Thu hoạch & Lô (`HarvestBatch`)** | Xem / Tạo / Hủy | Xem / Tạo | Chỉ xem |
| **Override ngày cách ly PHI (BR-08)** | Có quyền (kèm lý do & audit log) | ❌ Chặn cứng | ❌ Chặn cứng |
| **Nhập kết quả kiểm nghiệm (`LabTest`)** | Có quyền | Có quyền | Có quyền |
| **Hủy kết quả kiểm nghiệm (`LabTest`)** | Có quyền | ❌ Chặn | ❌ Chặn |
| **Tạo / Hủy phiếu bán hàng (`Sale`)** | Có quyền | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Thu tiền & Hủy thanh toán (`Payment`)** | Có quyền | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Sổ thu chi (`LedgerEntry`)** | Toàn quyền | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Báo cáo tài chính (P&L, Giá thành/kg, Công nợ)** | Toàn quyền xem | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Báo cáo kỹ thuật (Tồn kho, Cảnh báo PHI)** | Có quyền xem | Có quyền xem | Có quyền xem |
| **Giao việc & Cập nhật tiến độ (`Task`)** | Toàn quyền | Cập nhật tiến độ / Tạo | Tạo / Xem |

---

## 2. Danh mục quy tắc nghiệp vụ cốt lõi (BR-01 đến BR-24)

### 2.1. Phân quyền & Bảo mật (BR-01 đến BR-04)
- **BR-01, BR-02 (Farm Scoped & Anti-IDOR):** Mọi tài nguyên thuộc vườn phải được kiểm tra quyền sở hữu/thành viên. Tuyệt đối không cho phép truy cập chéo dữ liệu giữa các vườn khác nhau.
- **BR-03 (Audit Trail & Soft Void):** Không xóa cứng (`DELETE`) các chứng từ tài chính, bán hàng, thu hoạch hay nhật ký đã phát sinh. Dùng cơ chế `status = VOIDED` kèm lý do (`void_reason`), người hủy (`voided_by`), thời điểm hủy (`voided_at`) và ghi nhật ký kiểm toán `AuditLog`.
- **BR-04 (Bảo vệ chủ vườn cuối cùng):** Không cho phép xóa hoặc hạ quyền thành viên `OWNER` duy nhất còn lại của vườn.

### 2.2. Nhật ký canh tác & Quản lý thuốc BVTV (BR-05 đến BR-07)
- **BR-05 (Ngày cách ly bắt buộc):** Mọi vật tư thuộc nhóm thuốc bảo vệ thực vật (`PESTICIDE`) bắt buộc phải có thông số `phi_days` (Pre-Harvest Interval - số ngày cách ly tối thiểu trước khi thu hoạch).
- **BR-06 (Danh mục vật tư sầu riêng):** Cảnh báo nếu sử dụng hoạt chất cấm hoặc chưa được đăng ký sử dụng trên cây sầu riêng theo danh mục Cục BVTV.
- **BR-07 (Tự động tính chi phí vật tư):** Chi phí phát sinh từ nhật ký tự động tính: `total_cost = quantity * unit_cost`.

### 2.3. Thu hoạch & An toàn PHI (BR-08 đến BR-11)
- **BR-08 (Kiểm tra ngày cách ly thu hoạch):** Ngày thu hoạch của lô (`harvest_date`) bắt buộc phải $\ge$ ngày cách ly an toàn (`phi_safe_date`). Nếu vi phạm:
  - `WORKER` và `ADVISOR`: Bị chặn cứng (HTTP 409 `phi_not_elapsed`).
  - `OWNER`: Được phép duyệt vượt rào (`override_reason`), hệ thống tự động ghi sự kiện `PHI_OVERRIDE` vào `AuditLog`.
- **BR-09 (Định danh duy nhất mã lô):** Mã lô thu hoạch (`batch_code`) phải là duy nhất trong phạm vi mỗi trang trại (ràng buộc DB `UniqueConstraint(fields=['farm', 'batch_code'])`).
- **BR-10 (Quản lý phẩm cấp tồn kho):** Quản lý sản lượng chi tiết theo phẩm cấp `BatchStock` (`GRADE_1`, `GRADE_2`, `GRADE_3`, `REJECT`). Ràng buộc DB: $0 \le \text{remaining\_kg} \le \text{qty\_kg}$.
- **BR-11 (Bảo vệ lô đã phát sinh giao dịch):** Không cho phép hủy lô thu hoạch nếu đã phát sinh phiếu bán hàng (`remaining_kg < total_kg`).

### 2.4. Kiểm nghiệm chất lượng & Tiêu chuẩn xuất khẩu (BR-12, BR-13)
- **BR-12 (Kết quả kiểm nghiệm):** `LabTest.result` bắt buộc là `PASS` (Đạt) hoặc `FAIL` (Không đạt).
- **BR-13 (Kiểm soát xuất bán & Tiêu chuẩn xuất khẩu):**
  - **Bán thông thường:** Chỉ các lô đã có kết quả kiểm nghiệm `PASSED` mới được xuất kho bán. Lô `PENDING` (chưa kiểm nghiệm), `FAILED` hoặc `VOIDED` đều bị chặn (HTTP 409). Trạng thái của lô cập nhật theo kết quả `LabTest` còn hiệu lực (`ACTIVE`) mới nhất theo `tested_date`.
  - **Bán xuất khẩu (`destination = "EXPORT"`):**
    1. Chỉ cho phép xuất bán phẩm cấp `GRADE_1` (Loại 1 xuất khẩu) hoặc `GRADE_2`. Nghiêm cấm xuất bán `GRADE_3` hoặc `REJECT`.
    2. Lô thu hoạch phải có kiểm nghiệm đạt chuẩn (`PASS`) còn thời hạn hiệu lực (`valid_until >= sale_date`).
    3. Giá trị đo thực tế không được vượt ngưỡng quy định: `result_value <= limit_value`.
    4. Dư lượng kim loại nặng (Cadmium) không được vượt ngưỡng cho phép xuất khẩu sang thị trường mục tiêu (ví dụ: `cadmium_ppm <= 0.05`).

### 2.5. Bán hàng, Tồn kho & Thanh toán (BR-14 đến BR-19)
- **BR-14 (Giao dịch an toàn & Chống Deadlock):** Tạo phiếu bán dùng Database Transaction + Row Locking (`select_for_update`). Các dòng tồn kho `BatchStock` được sắp xếp theo ID tăng dần trước khi khóa hàng tránh deadlock khi có nhiều giao dịch đồng thời.
- **BR-15, BR-16 (Nguyên tắc chống tính trùng doanh thu & chi phí):**
  - Doanh thu bán hàng **chỉ** ghi nhận từ `Sale` (trạng thái `CONFIRMED`).
  - Tiền thanh toán thực tế **chỉ** ghi nhận từ `Payment` (trạng thái `ACTIVE`).
  - `LedgerEntry` **chỉ** lưu chi phí (`EXPENSE`) và thu khác (`OTHER_INCOME`). Chi phí vật tư phát sinh từ nhật ký tự động sinh bút toán vào `LedgerEntry`.
- **BR-17 (Trừ tồn kho tự động):** Khi tạo phiếu bán, `qty_kg` được trừ trực tiếp đồng bộ trên cả `BatchStock.remaining_kg` và `HarvestBatch.remaining_kg`.
- **BR-18 (Kiểm soát công nợ & Trạng thái thanh toán):** Tổng các khoản thanh toán không được vượt quá tổng tiền phiếu (`total_amount`). Trạng thái `payment_status` tự động suy ra: `UNPAID` (chưa thanh toán), `PARTIAL` (thanh toán một phần), `PAID` (đã thu đủ).
- **BR-19 (Hủy phiếu & Hoàn tồn kho):** Không cho phép hủy phiếu bán nếu còn khoản thanh toán hiệu lực (phải hủy các `Payment` trước). Khi hủy phiếu bán thành công, hệ thống tự động hoàn lại tồn kho `remaining_kg` cho `BatchStock` và `HarvestBatch`.

### 2.6. Mùa vụ & Tiến độ (BR-20, BR-21)
- **BR-20 (Mỗi vườn chỉ 1 mùa vụ hoạt động):** Mỗi trang trại tại một thời điểm chỉ được phép có tối đa 1 mùa vụ ở trạng thái `ACTIVE` (bảo vệ ở tầng DB bằng partial unique constraint).
- **BR-21 (Thứ tự tiến độ sinh trưởng):** Thứ tự các mốc ngày trong mùa vụ phải tuần tự: `flower_induction_date < fruit_set_date < expected_harvest_date`.

### 2.7. Quản lý công việc (BR-22, BR-23)
- **BR-22 (Việc lặp tự sinh chu kỳ mới):** Khi một công việc có thiết lập lặp lại (`is_recurring = True`) được đánh dấu hoàn thành (`COMPLETED`), hệ thống tự động khởi tạo công việc tiếp theo với `due_date = due_date_hiện_tại + recurring_interval_days`.
- **BR-23 (Bảo vệ công việc hệ thống):** Các công việc do hệ thống tự động sinh (`is_system = True` như lịch lấy mẫu kiểm nghiệm, cảnh báo cách ly) không cho phép người dùng thay đổi tiêu đề (`title`), mô tả (`description`) hay loại công việc (`task_type`).

### 2.8. Tính toán giá thành & Phân bổ chi phí (BR-24)
- **BR-24 (Giá thành sản xuất theo kg):** Giá thành của từng lô đất = Chi phí trực tiếp + Chi phí chung phân bổ theo tỷ lệ diện tích đất.

---

## 3. Mục 16: Báo cáo Quản trị & Bộ Dữ Liệu Mẫu Tính Tay (Mục 16.2)

### 3.1. Danh mục các báo cáo
1. **Báo cáo Lãi Lỗ (`/reports/profit-loss/`):**
   $$\text{Doanh Thu Bán Hàng} + \text{Thu Khác} - \text{Tổng Chi Phí} = \text{Lợi Nhuận Ròng}$$
2. **Báo cáo Giá Thành / kg (`/reports/cost-per-kg/`):** Phân tích chi tiết giá thành từng lô và giá thành bình quân toàn vườn.
3. **Báo cáo Công Nợ Người Mua (`/reports/receivables/`):** Tổng tiền xuất bán, tiền đã thu, nợ tồn đọng chi tiết theo từng đối tác mua hàng (Buyer).
4. **Báo cáo Tồn Kho (`/reports/stock-inventory/`):** Tồn kho kg theo từng grade, giá trị tồn kho ước tính.
5. **Báo cáo Cảnh Báo An Toàn PHI (`/reports/phi-warnings/`):** Cảnh báo trạng thái an toàn thu hoạch của tất cả các lô đất.

### 3.2. Bộ Dữ Liệu Mẫu Tính Tay Giá Thành (Mục 16.2)

Xét trang trại gồm **2 lô đất** với tổng diện tích **5.0 ha**:
- **Lô 1 (Lô A1 - Giống Ri6):** Diện tích $S_1 = 2.0\text{ ha}$ (chiếm $\frac{2.0}{5.0} = 40\%$ diện tích vườn).
- **Lô 2 (Lô A2 - Giống Monthong):** Diện tích $S_2 = 3.0\text{ ha}$ (chiếm $\frac{3.0}{5.0} = 60\%$ diện tích vườn).

#### Chi phí phát sinh trong mùa vụ:
1. **Chi phí trực tiếp Lô 1:** $C_{\text{trực tiếp 1}} = 30.000.000\text{ đ}$ (phân bón, công tỉa cành Lô 1).
2. **Chi phí trực tiếp Lô 2:** $C_{\text{trực tiếp 2}} = 45.000.000\text{ đ}$ (phân bón, phòng trừ nấm Lô 2).
3. **Chi phí chung toàn trang trại (`plot = NULL`):** $C_{\text{chung}} = 50.000.000\text{ đ}$ (tiền điện bơm tưới trạm bơm trung tâm, tiền thuê đất, bảo dưỡng máy móc).

#### Phân bổ chi phí chung theo diện tích (BR-24):
- Phân bổ cho Lô 1:
  $$C_{\text{phân bổ 1}} = 50.000.000 \times 40\% = 20.000.000\text{ đ}$$
  $$\Rightarrow \text{Tổng chi phí Lô 1} = 30.000.000 + 20.000.000 = 50.000.000\text{ đ}$$
- Phân bổ cho Lô 2:
  $$C_{\text{phân bổ 2}} = 50.000.000 \times 60\% = 30.000.000\text{ đ}$$
  $$\Rightarrow \text{Tổng chi phí Lô 2} = 45.000.000 + 30.000.000 = 75.000.000\text{ đ}$$
- **Tổng chi phí toàn trang trại:** $50.000.000 + 75.000.000 = 125.000.000\text{ đ}$.

#### Sản lượng thu hoạch thực tế:
- Lô 1 thu hoạch: $Q_1 = 2.500\text{ kg}$.
- Lô 2 thu hoạch: $Q_2 = 5.000\text{ kg}$.
- Tổng sản lượng toàn vườn: $Q_{\text{tổng}} = 2.500 + 5.000 = 7.500\text{ kg}$.

#### Kết quả tính giá thành / kg:
- **Giá thành Lô 1:**
  $$\text{Cost/kg}_1 = \frac{50.000.000\text{ đ}}{2.500\text{ kg}} = 20.000\text{ đ/kg}$$
- **Giá thành Lô 2:**
  $$\text{Cost/kg}_2 = \frac{75.000.000\text{ đ}}{5.000\text{ kg}} = 15.000\text{ đ/kg}$$
- **Giá thành bình quân toàn trang trại:**
  $$\text{Cost/kg}_{\text{TB}} = \frac{125.000.000\text{ đ}}{7.500\text{ kg}} \approx 16.667\text{ đ/kg}$$

---

## 4. Mục 22: Quy Tắc Tính PHI & Kiểm Soát Chỉ Tiêu Xuất Khẩu

### 4.1. Quy tắc đếm ngày an toàn cách ly (PHI)
- Xét tất cả các lần phun thuốc bảo vệ thực vật (`product.kind == 'PESTICIDE'`) trên lô đất đang hoạt động (`status = ACTIVE`).
- Thuật toán xác định:
  $$\text{phi\_safe\_date} = \max(\text{activity\_date} + \text{phi\_days})$$
- Phun cùng ngày thu hoạch (`activity_date <= harvest_date`) cũng bị coi là vi phạm nếu chưa đủ số ngày cách ly quy định.

### 4.2. Kiểm soát chỉ tiêu khi bán hàng xuất khẩu (BR-13)
Khi phiếu bán có `destination == 'EXPORT'` hoặc người mua là khách xuất khẩu (`buyer.is_export == True`):
1. Không cho phép bán sản phẩm phẩm cấp `GRADE_3` hoặc `REJECT`.
2. Lô xuất khẩu bắt buộc phải có kết quả kiểm nghiệm `LabTest` hợp lệ, đạt chuẩn (`PASS`).
3. Kết quả kiểm nghiệm phải còn trong thời hạn hiệu lực tính đến ngày xuất bán (`valid_until >= sale_date`).
4. Nếu kiểm tra các chỉ tiêu cụ thể (như Cadmium, Chlorpyrifos):
   - Hàm lượng đo được không vượt ngưỡng cho phép: $\text{result\_value} \le \text{limit\_value}$.
   - Dư lượng kim loại nặng Cadmium không vượt quá $0.05\text{ ppm}$ theo tiêu chuẩn xuất khẩu sầu riêng tươi.

---

## 5. Chuẩn Hóa Đường Dẫn URL API (API Conventions)

Hệ thống hỗ trợ đồng thời cả hai chuẩn URL để đảm bảo tương thích ngược và tính nhất quán với đặc tả:
- **Lô thu hoạch:**
  - Chuẩn đặc tả: `/api/v1/farms/{farm_id}/batches/`
  - Tương thích ngược: `/api/v1/farms/{farm_id}/harvest-batches/`
- **Thu tiền bán hàng:**
  - Chuẩn đặc tả: `POST /api/v1/farms/{farm_id}/sales/{id}/payments/`
  - Tương thích ngược: `POST /api/v1/farms/{farm_id}/sales/{id}/add_payment/`
