# Kịch bản thuyết trình Taipei Subway - 10 phút

## Phân bổ thời gian

| Thời gian | Nội dung |
| --- | --- |
| 0:00 - 0:45 | Mở đầu và bối cảnh |
| 0:45 - 2:00 | Phát biểu bài toán |
| 2:00 - 2:45 | Kiến trúc hệ thống |
| 2:45 - 3:35 | Nguồn và cách truy xuất dữ liệu |
| 3:35 - 6:15 | Cách giải và thuật toán |
| 6:15 - 8:40 | Demo |
| 8:40 - 9:40 | Kết quả và giới hạn |
| 9:40 - 10:00 | Kết luận |

## Kịch bản nói

### 0:00 - 0:45 | Mở đầu

> Em xin kính chào thầy cô và các bạn. Nhóm em xin trình bày dự án **Taipei Subway**, một ứng dụng web hỗ trợ định tuyến trên mạng MRT Đài Bắc, tích hợp dữ liệu GIS.
>
> Thay vì yêu cầu chọn sẵn ga khởi hành và ga đích, hệ thống tiếp nhận hai vị trí bất kỳ trên bản đồ, xác định ga phù hợp, tính hành trình MRT và trực quan hóa lộ trình.

### 0:45 - 2:00 | Bài toán đặt ra

> Đầu vào là hai tọa độ: điểm xuất phát và điểm đích do người dùng lựa chọn.
>
> Đầu ra là một hành trình hoàn chỉnh, gồm đoạn đi bộ tới ga vào, phần di chuyển bằng MRT, các bước chuyển tuyến nếu có và đoạn đi bộ từ ga ra tới đích.
>
> Bài toán đặt ra ba yêu cầu. Trước hết, vị trí được chọn thường không trùng với nhà ga. Hệ thống cần xác định ga có thể tiếp cận hợp lý theo mạng đường đi bộ.
>
> Tiếp theo, mạng MRT có nhiều ga trung chuyển. Nếu mỗi ga chỉ là một đỉnh, chi phí chuyển tuyến sẽ không được mô hình hóa đầy đủ.
>
> Cuối cùng, kết quả cần thích ứng khi ga tạm dừng phục vụ, đoạn tuyến bị khóa hoặc mưa lớn làm tăng chi phí đi bộ.

### 2:00 - 2:45 | Kiến trúc hệ thống

> Hệ thống được tổ chức theo mô hình **modular monolith**, gọn để triển khai cục bộ nhưng vẫn phân tách rõ trách nhiệm.
>
> Kiến trúc gồm bốn khối: giao diện **MapLibre**; API **FastAPI**; lớp dịch vụ với GIS loader, bộ tìm kiếm trên mạng đi bộ, route engine và runtime cache; cuối cùng là lớp dữ liệu GIS.
>
> Khi người dùng chọn hai điểm, frontend gọi `/api/gis/route/points` và gửi kèm kịch bản vận hành nếu có. Backend áp dụng ràng buộc trong phạm vi từng yêu cầu, tính hành trình, ghép dữ liệu hình học và trả kết quả cho bản đồ. Trạng thái của từng người dùng vì vậy được tách biệt.

### 2:45 - 3:35 | Nguồn và cách truy xuất dữ liệu

> Hệ thống sử dụng quy trình tiền xử lý thay vì truy vấn Internet trong từng lần định tuyến. Dữ liệu được chuẩn hóa và lưu cục bộ trước khi ứng dụng khởi chạy.
>
> Dữ liệu MRT gồm `network_topology.json` cho quan hệ ga, tuyến và segment; `stations.geojson`, `lines.geojson` cho hình học bản đồ; cùng `station_access_points.geojson` cho các điểm tiếp cận ga. Dữ liệu đường đi bộ lấy từ **OpenStreetMap**, được tiền xử lý bằng **OSMnx** và lưu thành walk network.
>
> Khi mở trang, frontend gọi `GET /api/gis/network` để tải ga, tuyến và thông tin bản đồ. Khi định tuyến, GIS loader đọc topology và GeoJSON. Walk graph cùng các chỉ mục hình học được lưu cache và tái sử dụng. Lần truy vấn đầu tiên chịu chi phí khởi tạo; các lần tiếp theo phản hồi nhanh hơn.

### 3:35 - 4:25 | Mô hình đồ thị

> Lõi thuật toán là **đồ thị trạng thái mở rộng**. Mỗi đỉnh là cặp `(station, line)`, cho biết hành khách đang ở ga nào và trên tuyến nào.
>
> Chẳng hạn, tại Taipei Main Station, trạng thái ở Red Line khác với trạng thái ở Blue Line. Việc đổi tuyến bắt buộc đi qua cạnh `transfer` và phát sinh chi phí.
>
> Đồ thị có ba loại cạnh:
>
> - `ride`: đi tàu giữa hai ga liền kề trên cùng một tuyến;
> - `transfer`: chuyển tuyến tại cùng một ga;
> - `walk-transfer`: đi bộ giữa hai ga gần nhau hoặc đi vòng khi có đoạn bị chặn.
>
> Mô hình này giúp đánh giá chính xác chi phí chuyển tuyến và hạn chế hành trình vòng không cần thiết.

### 4:25 - 5:15 | A* và Dijkstra

> Trên đồ thị trạng thái, route engine sử dụng thuật toán **A\***.
>
> Với mỗi trạng thái `n`, A* xếp ưu tiên theo công thức `f(n) = g(n) + h(n)`. `g(n)` là chi phí đã tích lũy, còn `h(n)` là ước lượng chi phí tới đích.
>
> Do mỗi ga có tọa độ địa lý, hệ thống tính `h(n)` bằng khoảng cách Haversine tới ga đích chia cho tốc độ tàu tối đa `80 km/h`. Heuristic này hướng quá trình tìm kiếm về phía đích.
>
> Dijkstra là trường hợp đặc biệt của A* khi heuristic bằng 0. Với dữ liệu GIS sẵn có, A* tận dụng thêm thông tin không gian và phù hợp hơn cho bài toán của nhóm.

### 5:15 - 6:15 | Luồng xử lý runtime và hàm chi phí

> Luồng xử lý runtime gồm năm bước. Backend nhận hai tọa độ, sau đó dùng **walk network** và station access points để tìm các ga vào-ra ứng viên. Bước này áp dụng multi-source Dijkstra từ một số điểm snap gần nhất và dừng sớm khi đã đủ ứng viên phù hợp.
>
> Backend xét các cặp ga hợp lệ và chạy A*. Phương án tốt nhất được so sánh với lựa chọn đi bộ hoàn toàn để tránh đề xuất MRT cho quãng đường quá ngắn. Cuối cùng, backend ghép dữ liệu hình học của toàn bộ hành trình.
>
> Hàm chi phí là vector `(T, W, N_transfer, N_stop)`: ưu tiên thời gian, sau đó xét thời gian đi bộ, số lần chuyển tuyến và số chặng. Chi phí đi bộ được nhân hệ số `5.0` để tránh lạm dụng đi bộ thay cho MRT.

### 6:15 - 8:40 | Demo

> Sau đây, em xin trình bày luồng demo chính.

**[Thao tác 1 - mở `http://127.0.0.1:8010/`]**

> Đây là GIS Route Studio. Em chọn điểm xuất phát, điểm đích và yêu cầu hệ thống tính đường.

**[Thao tác 2 - chọn hai điểm đã tập trước, ưu tiên một hành trình đủ dài và có chuyển tuyến]**

> Frontend gửi tọa độ tới API. Backend xác định ga vào, ga ra, chạy A* và trả về hành trình.

**[Thao tác 3 - chỉ vào route và bảng tóm tắt]**

> Bản đồ hiển thị đoạn đi bộ tới ga vào, phần di chuyển bằng MRT, bước chuyển tuyến nếu có và đoạn đi bộ tới đích. Bảng bên cạnh tóm tắt thời gian cùng trình tự di chuyển.

> Tiếp theo, em minh họa khả năng thích ứng với thay đổi vận hành.

**[Thao tác 4 - mở tab `http://127.0.0.1:8010/admin`]**

> Tại Admin Console, em khóa một ga hoặc đoạn tuyến nằm trên lộ trình vừa tính.

**[Thao tác 5 - lưu kịch bản vận hành, quay lại tab GIS và tính lại lộ trình]**

> Khi tính lại, lộ trình thay đổi vì backend đã áp dụng kịch bản vận hành vào đồ thị runtime. Kết quả được tái tính theo ràng buộc mới, thay vì chỉ thay đổi phần hiển thị.

### 8:40 - 9:40 | Kết quả và giới hạn

> Sau khi cache được làm nóng, tổng thời gian phản hồi API khoảng `0.13 giây`; riêng bước A* dưới `10 ms`. Chi phí lớn hơn nằm ở lần nạp walk graph đầu tiên và bước tìm ga ứng viên.
>
> Phiên bản hiện tại vẫn dùng topology tĩnh và đăng nhập admin ở mức demo. Hướng tiếp theo là tích hợp GTFS theo lịch chạy thực tế và bổ sung xác thực cho khu vực quản trị.

### 9:40 - 10:00 | Kết luận

> Dự án đã xây dựng được một quy trình định tuyến MRT hoàn chỉnh: tiếp nhận vị trí trên bản đồ, xác định ga phù hợp qua walk network, tìm đường bằng A* trên đồ thị `(station, line)` và tái tính hành trình khi điều kiện vận hành thay đổi.
>
> Em xin cảm ơn thầy cô và các bạn đã lắng nghe. Nhóm em xin nhận câu hỏi.

## Checklist trước khi demo

1. Chạy server:

   ```powershell
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
   ```

2. Mở sẵn hai tab:
   - `http://127.0.0.1:8010/`
   - `http://127.0.0.1:8010/admin`
3. Chọn và thử trước một cặp điểm đủ xa để lộ trình MRT hiển thị rõ ràng.
4. Xác định trước một ga hoặc đoạn tuyến nằm trên lộ trình để khóa trong tab admin.
5. Đặt lại kịch bản vận hành trước khi bắt đầu demo.
6. Chuẩn bị ảnh chụp lộ trình trước và sau khi khóa tuyến vì MapLibre và OSM tiles cần kết nối mạng.

## Sơ đồ kiến trúc để đưa lên slide

```text
Trình duyệt
  |-- GIS Studio (MapLibre)
  `-- Admin Console (kịch bản vận hành trong localStorage)
          |
          v
FastAPI: /api/gis/network, /api/gis/route/points, /api/admin/scenarios
          |
          v
Lớp dịch vụ
  |-- GIS loader + runtime cache
  |-- Tìm kiếm trên walk network: multi-source Dijkstra
  |-- Route engine: A* trên đồ thị trạng thái (station, line)
  `-- Bộ xử lý kịch bản vận hành
          |
          v
Dữ liệu: topology MRT + GeoJSON + station access points + walk network
```

## Sơ đồ luồng dữ liệu để đưa lên slide

```text
OpenStreetMap --OSMnx + scripts/map--> walk network + OSM enrichment
QGIS / dữ liệu MRT đã chuẩn hoá ------> topology + stations/lines/access-points GeoJSON
                                              |
                                              v
                               GIS loader + cache cấu trúc runtime
                                              |
                     +------------------------+------------------------+
                     v                                                 v
        GET /api/gis/network                               POST /api/gis/route/points
        frontend hiển thị bản đồ                           backend tính hành trình
```

## Câu trả lời ngắn khi bị hỏi

**Kiến trúc hệ thống được tổ chức như thế nào?**

> Hệ thống được tổ chức theo mô hình modular monolith, gồm giao diện MapLibre, API FastAPI, các dịch vụ chuyên biệt và lớp dữ liệu GIS. Kiến trúc này đủ gọn để triển khai cục bộ, đồng thời phân tách rõ giao diện, điều phối API, thuật toán và dữ liệu.

**Dữ liệu lấy từ đâu và có gọi trực tiếp lên OSM khi tìm đường không?**

> Dữ liệu MRT được chuẩn hóa thành topology và các lớp GeoJSON. Dữ liệu đường đi bộ cùng enrichment được lấy từ OpenStreetMap thông qua OSMnx trong bước tiền xử lý. Khi người dùng yêu cầu định tuyến, backend sử dụng dữ liệu cục bộ và runtime cache; hệ thống không truy vấn trực tiếp OSM cho từng yêu cầu.

**Tại sao không dùng Dijkstra làm thuật toán chính?**

> Dijkstra là trường hợp đặc biệt của A* khi heuristic bằng 0. Vì dữ liệu của dự án có tọa độ ga, A* có thể sử dụng khoảng cách tới đích để định hướng quá trình tìm kiếm.

**Tại sao đỉnh phải là `(station, line)` thay vì chỉ là `station`?**

> Vì cùng một ga nhưng đang ở hai tuyến khác nhau là hai trạng thái khác nhau. Tách theo `(station, line)` giúp mô hình hóa đúng chi phí chuyển tuyến.

**Walk network có thay thế bài toán định tuyến MRT không?**

> Không. Walk network xử lý kết nối từ điểm người dùng chọn tới ga vào và từ ga ra tới đích. Lõi định tuyến giữa các ga vẫn là A* trên mạng MRT.

**Kịch bản vận hành ảnh hưởng đến thuật toán như thế nào?**

> Backend áp dụng kịch bản vận hành trước khi định tuyến: ga hoặc segment bị khóa sẽ bị loại khỏi đồ thị runtime; vùng mưa làm tăng chi phí đi bộ. Sau đó, A* được chạy lại trên trạng thái mới.

**Nếu có thêm thời gian, nhóm sẽ phát triển gì?**

> Nhóm sẽ tích hợp GTFS để hỗ trợ lịch chạy động, nghiên cứu RAPTOR hoặc CSA cho định tuyến theo timetable và bổ sung cơ chế xác thực đầy đủ cho khu vực quản trị.
