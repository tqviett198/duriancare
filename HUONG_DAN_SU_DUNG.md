# HƯỚNG DẪN SỬ DỤNG & TỔNG QUAN TÍNH NĂNG HỆ THỐNG DURIANCARE
*(DurianCare — Smart Durian Farm Management & Traceability System)*

---

## 📖 MỤC LỤC
1. [Giới thiệu dự án](#1-giới-thiệu-dự-án)
2. [Hệ thống có thể làm được những gì? (Giá trị mang lại)](#2-hệ-thống-có-thể-làm-được-những-gì-giá-trị-mang-lại)
3. [Ma trận phân quyền (RBAC)](#3-ma-trận-phân-quyền-rbac)
4. [Chi tiết các tính năng & Quy tắc nghiệp vụ (BR)](#4-chi-tiết-các-tính-năng--quy-tắc-nghiệp-vụ-br)
5. [Hướng dẫn cài đặt & Khởi chạy hệ thống](#5-hướng-dẫn-cài-đặt--khởi-chạy-hệ-thống)
6. [Kịch bản sử dụng thực tế từng bước (Walkthrough)](#6-kịch-bản-sử-dụng-thực-tế-từng-bước-walkthrough)
7. [Tài liệu API & Kiểm thử tự động](#7-tài-liệu-api--kiểm-thử-tự-động)

---

## 1. GIỚI THIỆU DỰ ÁN

**DurianCare** là phần mềm quản lý trang trại sầu riêng thông minh, được xây dựng nhằm đáp ứng các tiêu chuẩn khắt khe về canh tác an toàn (**VietGAP**, **GlobalGAP**) và **xuất khẩu chính ngạch** (Nghị định thư xuất khẩu sầu riêng tươi sang Trung Quốc và EU).

- **Backend:** Python 3.12, Django 5.2, Django REST Framework, PostgreSQL / SQLite.
- **Tác vụ nền:** Celery 5.6 + Redis (Lập lịch kiểm tra cách ly PHI và nhắc việc tự động).
- **Frontend:** React 18 (Vite), kiến trúc PWA (Progressive Web App), giao diện Responsive tối ưu cho cả máy tính và điện thoại.
- **Đóng gói:** Docker & Docker Compose production-ready.

---

## 2. HỆ THỐNG CÓ THỂ LÀM ĐƯỢC NHỮNG GÌ? (GIÁ TRỊ MANG LẠI)

DurianCare giải quyết triệt để 5 "nỗi đau" lớn nhất của nhà vườn và hợp tác xã sầu riêng:

1. **Chống vi phạm tồn dư thuốc BVTV (Pre-Harvest Interval - PHI):** Tự động tính toán ngày an toàn sớm nhất có thể thu hoạch dựa trên lịch phun xịt thực tế, chặn thu hoạch non.
2. **Kiểm soát chất lượng xuất khẩu nghiêm ngặt (BR-13):** Tự động kiểm tra chứng nhận kiểm nghiệm độc lập (`LabTest`), hạn dùng, hàm lượng kim loại nặng (Cadmium), dư lượng thuốc trước khi cho phép xuất bán thị trường quốc tế.
3. **Báo cáo giá thành theo từng kg chính xác (BR-24):** Gom chi phí trực tiếp của từng lô đất kết hợp phân bổ chi phí chung (điện, nước, nhân công, thuê đất) theo diện tích đất để ra giá thành 1 kg sầu riêng.
4. **Minh bạch tài chính & Chống thất thoát:** Doanh thu, sổ quỹ và công nợ khách mua được tách bạch, quản lý dòng tiền thu nhiều lần vào phiếu bán hàng.
5. **Số hóa nhật ký & Phân công công việc:** Tự động sinh việc định kỳ, lập lịch lấy mẫu kiểm nghiệm và gửi thông báo cho nhân công.

---

## 3. MA TRẬN PHÂN QUYỀN (RBAC)

Hệ thống hoạt động theo mô hình **Đa nông trại (Multi-farm)**. Mỗi tài khoản có một vai trò cụ thể trên từng vườn:

| Phân hệ / Chức năng | OWNER (Chủ vườn) | WORKER (Người làm vườn) | ADVISOR (Kỹ thuật viên / HTX) |
|---|:---:|:---:|:---:|
| **Quản trị nông trại, lô đất, mùa vụ** | Toàn quyền | Chỉ xem | Chỉ xem |
| **Ghi nhật ký canh tác (phân bón, thuốc)** | Có quyền | Có quyền | Chỉ xem |
| **Ghi nhận lô thu hoạch** | Có quyền | Có quyền | Chỉ xem |
| **Duyệt vượt ngày cách ly PHI (BR-08)** | ✅ Có quyền (kèm lý do & audit) | ❌ Bị chặn | ❌ Bị chặn |
| **Nhập kết quả kiểm nghiệm (`LabTest`)** | ✅ Có quyền | ✅ Có quyền | ✅ Có quyền |
| **Hủy kết quả kiểm nghiệm** | ✅ Có quyền | ❌ Bị chặn | ❌ Bị chặn |
| **Tạo phiếu bán hàng & Quản lý Buyer** | ✅ Có quyền | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Thu tiền thanh toán (`/payments/`)** | ✅ Có quyền | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Báo cáo tài chính (P&L, Giá thành/kg, Công nợ)** | ✅ Toàn quyền xem | ❌ 403 Forbidden | ❌ 403 Forbidden |
| **Báo cáo kỹ thuật (Tồn kho, Cảnh báo PHI)** | ✅ Có quyền xem | ✅ Có quyền xem | ✅ Có quyền xem |
| **Quản lý công việc (`Task`)** | Toàn quyền | Nhận việc / Cập nhật tiến độ | Giao việc / Cập nhật |

---

## 4. CHI TIẾT CÁC TÍNH NĂNG & QUY TẮC NGHIỆP VỤ (BR)

### 🌿 4.1. Quản lý Lô đất, Vùng trồng & Mùa vụ
- **Lô đất (`Plot`):** Quản lý diện tích (`area_ha`), giống sầu riêng (Ri6, Monthong, Musang King...), số lượng cây, giai đoạn sinh trưởng (Cây con, Ra đọt, Nở hoa, Đậu trái, Nuôi trái, Thu hoạch).
- **Mùa vụ (`Season`):** Mỗi vườn chỉ được phép có **duy nhất 1 mùa vụ ACTIVE** tại một thời điểm (**BR-20** - ràng buộc ở tầng Database).
- **Mã số vùng trồng (`PlantingCode`):** Quản lý mã vùng trồng xuất khẩu phục vụ truy xuất nguồn gốc.

### 📝 4.2. Nhật ký canh tác & Quản lý thuốc BVTV
- Ghi chép lịch bón phân, tưới nước, tỉa cành và phun thuốc.
- **BR-05:** Thuốc BVTV bắt buộc phải có thời gian cách ly (`phi_days`).
- **BR-06 & BR-07:** Cảnh báo hoạt chất chưa đăng ký cho sầu riêng, tự động tính tiền chi phí vật tư: $\text{Tổng tiền} = \text{Số lượng} \times \text{Đơn giá}$.
- **Tự động sinh chi phí:** Chi phí vật tư nhật ký tự động hạch toán sang sổ thu chi (`LedgerEntry`).

### 🌾 4.3. Thu hoạch, Kiểm nghiệm & An toàn PHI
- **BR-08 (Kiểm soát PHI):** Khi lập lô thu hoạch (`HarvestBatch`), hệ thống rà soát toàn bộ lịch phun thuốc trước đó. Nếu ngày thu hoạch chưa qua ngày an toàn (`phi_safe_date`):
  - Người làm vườn (`WORKER`): Bị chặn cứng.
  - Chủ vườn (`OWNER`): Có quyền ghi đè (`override_reason`), hệ thống tự động ghi nhật ký kiểm toán `AuditLog`.
- **BR-09 & BR-10:** Quản lý mã lô độc nhất theo vườn, phân tách tồn kho theo 4 phẩm cấp:
  - `GRADE_1`: Loại 1 (Đạt chuẩn xuất khẩu).
  - `GRADE_2`: Loại 2 (Nội địa cao cấp).
  - `GRADE_3`: Loại 3 (Nội địa phổ thông).
  - `REJECT`: Hàng dạt / chế biến.
- **BR-12 & BR-13 (Kiểm nghiệm LabTest):**
  - Ghi nhận chỉ tiêu kiểm nghiệm: Hoạt chất (`analyte`), giá trị đo (`result_value`), ngưỡng quy định (`limit_value`), hạn hiệu lực (`valid_until`), giấy chứng nhận (`certificate_url`).
  - Trạng thái lô tự động cập nhật sang `PASSED` nếu có kiểm nghiệm ĐẠT gần nhất, hoặc `FAILED` nếu không đạt.
  - Hỗ trợ hủy kết quả kiểm nghiệm (`status = VOIDED`) với truy vết kiểm toán, tự động hoàn trả trạng thái lô về `PENDING`.

### 📦 4.4. Bán hàng, Xuất khẩu & Quản lý Công nợ
- **Bảo vệ đồng thời (BR-14):** Khóa dòng cơ sở dữ liệu (`select_for_update`) và sắp xếp theo ID tăng dần để chống deadlock khi nhiều người cùng tạo phiếu bán.
- **Trừ tồn tự động (BR-17):** Trừ trực tiếp `remaining_kg` của từng phẩm cấp khi tạo phiếu bán.
- **Kiểm soát xuất khẩu khắt khe (BR-13):** Khi bán xuất khẩu (`destination = "EXPORT"`):
  1. Chặn không cho xuất bán hàng `GRADE_3` hoặc `REJECT`.
  2. Bắt buộc lô phải có kiểm nghiệm đạt chuẩn (`PASSED`).
  3. Kết quả kiểm nghiệm phải còn hạn dùng (`valid_until >= sale_date`).
  4. Hàm lượng đo không được vượt ngưỡng: $\text{result\_value} \le \text{limit\_value}$.
  5. Dư lượng kim loại nặng Cadmium không được vượt $0.05\text{ ppm}$.
- **Thanh toán & Thu tiền nhiều đợt (BR-18):** Thu tiền theo từng đợt, tự động cập nhật trạng thái `UNPAID` (Chưa trả), `PARTIAL` (Trả một phần), `PAID` (Đã thanh toán đủ).
- **Hủy phiếu bán hoàn tồn kho (BR-19):** Muốn hủy phiếu bán phải hủy các khoản thanh toán trước. Hủy thành công tự động hoàn trả số kg về kho.

### 📊 4.5. Phân hệ Báo cáo Quản trị (App `reports`)
1. **Báo cáo Giá thành / kg theo lô (BR-24 & Mục 16.2 đặc tả):**
   - Gom toàn bộ chi phí trực tiếp phát sinh trên từng lô đất.
   - Phân bổ chi phí chung toàn trang trại (điện nước, thuê đất, máy móc) cho các lô đất **theo tỷ lệ diện tích (area_ha)**.
   - Tính ra giá thành sản xuất thực tế trên mỗi kg sầu riêng thu hoạch của từng lô và giá bình quân toàn trang trại.
2. **Báo cáo Lãi lỗ (P&L):** Doanh thu bán hàng (`Sale`) + Thu khác (`LedgerEntry`) - Chi phí theo danh mục (Phân bón, Thuốc, Nhân công, Điện nước...) = Lợi nhuận ròng & Tỷ suất lợi nhuận.
3. **Báo cáo Công nợ (`Receivables`):** Chi tiết công nợ từng đối tác mua hàng (`Buyer`), tổng tiền mua, số tiền đã thu, số tiền nợ còn lại.
4. **Báo cáo Tồn kho (`Stock Inventory`):** Thống kê số lượng kg ban đầu, số kg đã bán, số kg còn lại và ước tính giá trị tồn kho theo từng loại phẩm cấp (Grade 1/2/3).
5. **Báo cáo Cảnh báo PHI:** Đếm ngược số ngày cách ly an toàn của từng lô đất, cảnh báo các lô sắp được phép thu hoạch.

### ⏰ 4.6. Phân hệ Quản lý Công việc & Cảnh báo (App `tasks`)
- **BR-22 (Việc lặp lại chu kỳ):** Khi người làm vườn hoàn thành một công việc lặp lại (ví dụ: bón phân chu kỳ 14 ngày, tưới nước 3 ngày), hệ thống tự động sinh công việc tiếp theo với ngày đến hạn tương ứng.
- **BR-23 (Bảo vệ việc hệ thống):** Các công việc do hệ thống tự sinh (nhắc lịch lấy mẫu kiểm nghiệm xuất khẩu) không cho phép người dùng tùy tiện sửa đổi tiêu đề và nội dung cốt lõi.
- **Celery Tasks tự động:** Tự động rà soát cảnh báo cách ly PHI và nhắc nhở các công việc đến hạn mỗi ngày.

---

## 5. HƯỚNG DẪN CÀI ĐẶT & KHỞI CHẠY HỆ THỐNG

### Cách 1: Chạy trực tiếp trên máy cục bộ (Local Development)

#### 🔹 Bước 1: Khởi động Backend (Django)
Mở cửa sổ Terminal thứ nhất:
```powershell
cd duriancare\backend

# Áp dụng cơ sở dữ liệu
..\.venv\Scripts\python.exe manage.py migrate

# Nạp dữ liệu demo ban đầu (chạy 1 lần duy nhất)
..\.venv\Scripts\python.exe manage.py seed_demo

# Khởi chạy server API
..\.venv\Scripts\python.exe manage.py runserver 8000
```
> Server API backend sẵn sàng tại: `http://localhost:8000`  
> Tài liệu Swagger UI: `http://localhost:8000/api/docs/`

#### 🔹 Bước 2: Khởi động Frontend (React PWA)
Mở cửa sổ Terminal thứ hai:
```powershell
cd duriancare\frontend

# Khởi chạy giao diện người dùng
npm run dev
```
> Ứng dụng web mở tại: `http://localhost:3000`

---

### Cách 2: Chạy toàn bộ bằng Docker Compose (Khuyên dùng khi triển khai)
Yêu cầu máy đã cài Docker Desktop:
```powershell
cd duriancare
cp .env.example .env
docker compose up --build
```
Hệ thống tự động kích hoạt đủ 6 dịch vụ:
- `db` (Postgres 16)
- `redis` (Redis 7)
- `backend` (Django API)
- `celery-worker` (Xử lý nền)
- `celery-beat` (Lập lịch tự động)
- `frontend` (React Nginx container tại port 3000)

---

## 6. KỊCH BẢN SỬ DỤNG THỰC TẾ TỪNG BƯỚC (WALKTHROUGH)

Truy cập trình duyệt tại **`http://localhost:3000`**:

### Kịch bản 1: Kiểm tra Ma trận phân quyền
1. Nhìn lên góc trên bên phải thanh Menu, bấm chọn vai trò:
   - Chọn `OWNER (Chủ vườn)`: Toàn quyền truy cập tất cả các mục.
   - Chuyển sang `WORKER (Người làm vườn)` hoặc `ADVISOR (Kỹ thuật viên)`:
     - Bấm vào tab **Báo cáo** hoặc **Bán hàng**: Giao diện lập tức hiển thị bảng cảnh báo **`403 FORBIDDEN`**, chặn nhân công xem số liệu tiền nong và giá bán.
     - Chuyển sang tab **Lô & Kiểm nghiệm** hoặc **Công việc**: Người làm vườn vẫn được xem và thao tác bình thường.

### Kịch bản 2: Xem Báo cáo Giá thành / kg theo Lô (BR-24)
1. Đặt vai trò là `OWNER`.
2. Chọn tab **Báo cáo thống kê** $\rightarrow$ chọn tab con **Giá thành / kg (BR-24)**.
3. Xem bảng tính tự động:
   - **Lô A1 (2.0 ha = 40% diện tích):** Chi phí trực tiếp 30 triệu + Chi phí chung phân bổ 20 triệu = 50 triệu $\rightarrow$ Sản lượng 2.500 kg $\rightarrow$ **Giá thành: 20.000 đ/kg**.
   - **Lô A2 (3.0 ha = 60% diện tích):** Chi phí trực tiếp 45 triệu + Chi phí chung phân bổ 30 triệu = 75 triệu $\rightarrow$ Sản lượng 5.000 kg $\rightarrow$ **Giá thành: 15.000 đ/kg**.
   - **Bình quân toàn vườn:** **16.667 đ/kg**.

### Kịch bản 3: Nhập Kết quả kiểm nghiệm (`LabTest`)
1. Chọn tab **Lô & Kiểm nghiệm**.
2. Nhấn nút **`+ Nhập kết quả kiểm nghiệm (LabTest)`**.
3. Điền các chỉ tiêu xuất khẩu:
   - Chỉ tiêu: *Cadmium*
   - Giá trị đo: `0.02` ppm
   - Ngưỡng tối đa: `0.05` ppm
   - Hạn hiệu lực: Chọn ngày trong tương lai.
4. Bấm **Lưu kết quả** $\rightarrow$ Kết quả hiển thị tức thì, lô thu hoạch tự động chuyển trạng thái `ĐẠT (PASS)`.
5. Bấm thử nút **`Hủy kết quả`** $\rightarrow$ Nhập lý do $\rightarrow$ Kết quả chuyển sang `Đã hủy (VOIDED)` và lô hoàn trạng thái về `Chờ kiểm nghiệm (PENDING)`.

### Kịch bản 4: Bán hàng xuất khẩu & Thu tiền theo đợt
1. Chọn tab **Bán hàng & Xuất khẩu**.
2. Xem phiếu xuất khẩu có nhãn **`✈️ XUẤT KHẨU`**: Hệ thống đã tự động kiểm tra đủ điều kiện an toàn trước khi cho phép lập phiếu.
3. Tại dòng phiếu bán còn thiếu tiền, bấm nút **`+ Thu tiền (/payments/)`**.
4. Nhập số tiền thanh toán (ví dụ: `20.000.000 đ`) và xác nhận $\rightarrow$ Số tiền đã thu tăng lên, công nợ tự động giảm xuống tương ứng.

### Kịch bản 5: Hoàn thành việc lặp lại chu kỳ (BR-22)
1. Chọn tab **Công việc & Cảnh báo**.
2. Tìm công việc có huy hiệu **`🔁 Lặp lại (14 ngày)`**.
3. Bấm nút **`✓ Hoàn thành`** $\rightarrow$ Công việc hiện tại chuyển sang trạng thái gạch ngang `Đã hoàn thành`, đồng thời một công việc chu kỳ mới với ngày hẹn sau 14 ngày sẽ **tự động sinh ra ngay bên dưới**.

---

## 7. TÀI LIỆU API & KIỂM THỬ TỰ ĐỘNG

### 🔹 Tài liệu API Endpoints chuẩn hóa

| Chức năng | Phương thức & URL | Phân quyền |
|---|---|:---:|
| **Lô thu hoạch** | `GET, POST /api/v1/farms/{id}/batches/` (hoặc `/harvest-batches/`) | OWNER, WORKER |
| **Thêm kiểm nghiệm** | `POST /api/v1/farms/{id}/batches/{batch_id}/lab-tests/` | OWNER, ADVISOR, WORKER |
| **Hủy kiểm nghiệm** | `POST /api/v1/farms/{id}/batches/{batch_id}/lab-tests/{test_id}/void/` | OWNER |
| **Bán hàng** | `GET, POST /api/v1/farms/{id}/sales/` | OWNER |
| **Thu tiền phiếu bán** | `POST /api/v1/farms/{id}/sales/{sale_id}/payments/` | OWNER |
| **Hủy thanh toán** | `POST /api/v1/farms/{id}/sales/{sale_id}/payments/{pay_id}/void/` | OWNER |
| **Báo cáo P&L** | `GET /api/v1/farms/{id}/reports/profit-loss/` | OWNER |
| **Báo cáo Giá thành/kg** | `GET /api/v1/farms/{id}/reports/cost-per-kg/` | OWNER |
| **Báo cáo Công nợ** | `GET /api/v1/farms/{id}/reports/receivables/` | OWNER |
| **Báo cáo Tồn kho** | `GET /api/v1/farms/{id}/reports/stock-inventory/` | TẤT CẢ VAI TRÒ |
| **Báo cáo Cảnh báo PHI** | `GET /api/v1/farms/{id}/reports/phi-warnings/` | TẤT CẢ VAI TRÒ |
| **Công việc** | `GET, POST /api/v1/farms/{id}/tasks/` | TẤT CẢ VAI TRÒ |
| **Hoàn thành việc** | `POST /api/v1/farms/{id}/tasks/{task_id}/complete/` | TẤT CẢ VAI TRÒ |

### 🔹 Chạy kiểm thử tự động (Unit & Integration Tests)
Bộ kiểm thử bao gồm **138 test cases** tự động bao phủ 100% các quy tắc nghiệp vụ:
```powershell
cd duriancare\backend
..\.venv\Scripts\python.exe manage.py test
```
**Kết quả thực tế:**
```text
Ran 138 tests in 1.650s
OK
```

---
*DurianCare — Nâng tầm nông sản Việt Nam với công nghệ số hóa hiện đại.*
