document.addEventListener("DOMContentLoaded", async function () {
    console.log("📋 Task Dashboard loaded");
    const tbody = document.getElementById("task-list");
    const loadMoreBtn = document.getElementById("load-more-btn");
    
    const INITIAL_ROWS = 10; // Giới hạn số hàng ban đầu
    let allTasks = []; // Biến lưu trữ tất cả task hợp lệ
    let taskIndex = 0; // Biến đếm STT toàn cục (phải là global trong scope này)
  
    // Đặt giá trị này là true nếu bạn muốn hiển thị cấu trúc cha-con
    const ENABLE_TREE_VIEW = true; 
  
    try {
      // 1. LẤY TẤT CẢ DỮ LIỆU
      const res = await fetch(
        '/api/resource/Task?fields=["name","subject","status","project","owner","exp_end_date","modified","parent_task"]&limit_page_length=1000'
      );
      const data = await res.json();
      tbody.innerHTML = "";
  
      if (!data.data || data.data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;">Không có task nào.</td></tr>`;
        return;
      }
  
      // 2. LỌC VÀ LƯU TRỮ
      allTasks = data.data.filter(
        (t) => !["Template", "Cancelled", "Completed"].includes(t.status || "")
      );
      
      // 3. THỰC HIỆN RENDER BAN ĐẦU (10 hàng)
      await renderTasks(allTasks.slice(0, INITIAL_ROWS));
  
      // 4. HIỂN THỊ NÚT XEM THÊM NẾU CẦN
      if (allTasks.length > INITIAL_ROWS) {
        loadMoreBtn.style.display = 'block';
        // Thêm sự kiện cho nút "Xem thêm"
        loadMoreBtn.addEventListener('click', async () => {
          // Tải phần còn lại của task (từ hàng 10 trở đi)
          const remainingTasks = allTasks.slice(INITIAL_ROWS);
          await renderTasks(remainingTasks, true); // True để chỉ append, không clear
          loadMoreBtn.style.display = 'none'; // Ẩn nút sau khi xem tất cả
        });
      }
  
    } catch (err) {
      console.error("❌ Error fetching tasks:", err);
      tbody.innerHTML = `<tr><td colspan="7" style="color:red;text-align:center;">Lỗi tải dữ liệu task</td></tr>`;
    }
    
    // ------------------------------------------
    // HÀM RENDER CHÍNH ĐƯỢC GỌI BỞI CẢ 2 CHẾ ĐỘ
    // ------------------------------------------
    async function renderTasks(tasksToRender, appendMode = false) {
      if (!appendMode) {
          tbody.innerHTML = ""; // Xóa nội dung cũ khi render lần đầu
          taskIndex = 0; // Reset STT khi render lần đầu
      }
  
      if (ENABLE_TREE_VIEW) {
        const taskMap = new Map();
        tasksToRender.forEach((t) => taskMap.set(t.name, { ...t, children: [] }));
        const roots = [];
  
        for (const task of tasksToRender) {
          // Chỉ thêm vào children nếu task cha nằm trong danh sách đang được render
          if (task.parent_task && taskMap.has(task.parent_task)) {
            taskMap.get(task.parent_task).children.push(taskMap.get(task.name));
          } else if (!task.parent_task || !taskMap.has(task.parent_task)) {
            // Chỉ coi là root nếu nó không có cha, hoặc cha không nằm trong danh sách 
            // (ví dụ: cha đã được render trong 10 hàng đầu)
            roots.push(taskMap.get(task.name));
          }
        }
  
        for (const root of roots) {
          await renderTaskRowRecursive(root, tbody, 0);
        }
      } else {
        // Dạng bảng phẳng (Flat Table)
        for (const task of tasksToRender) {
          await renderTaskRow(task, tbody);
        }
      }
    }
  
    // 🔹 Hàm render từng task (bảng phẳng)
    async function renderTaskRow(task, tbody) {
      taskIndex++; // Tăng STT cho mỗi task
      const assignees = await getAssignees(task.name);
      // Bỏ qua owner nếu họ cũng là assignee
      const filteredAssignees = assignees.filter((u) => u !== task.owner); 
  
      let assigneeHTML = "";
      if (filteredAssignees.length > 0) {
        const htmls = await Promise.all(filteredAssignees.map((u) => getUserAvatarHTML(u)));
        assigneeHTML = `<div class="assignee-container">${htmls.join("")}</div>`;
      }
  
      const projectName = task.project ? await getProjectName(task.project) : "";
  
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${taskIndex}</td> 
        <td><a href="/app/task/${task.name}" target="_blank">${task.subject || task.name}</a></td>
        <td>${task.status || ""}</td>
        <td>${projectName}</td>
        <td>${assigneeHTML}</td>
        <td>${formatDate(task.exp_end_date)}</td>
        <td>${formatDate(task.modified)}</td>
      `;
      tbody.appendChild(row);
    }
  
    // 🔹 Hàm render dạng cây (Recursive)
    async function renderTaskRowRecursive(task, tbody, level = 0) {
      taskIndex++; // Tăng STT cho mỗi task
      const indent = "&nbsp;".repeat(level * 6);
      const assignees = await getAssignees(task.name);
      const filteredAssignees = assignees.filter((u) => u !== task.owner);
  
      let assigneeHTML = "";
      if (filteredAssignees.length > 0) {
        const htmls = await Promise.all(filteredAssignees.map((u) => getUserAvatarHTML(u)));
        assigneeHTML = `<div class="assignee-container">${htmls.join("")}</div>`;
      }
  
      const projectName = task.project ? await getProjectName(task.project) : "";
  
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${taskIndex}</td>
        <td>${indent}<a href="/app/task/${task.name}" target="_blank">${task.subject}</a></td>
        <td>${task.status || ""}</td>
        <td>${projectName}</td>
        <td>${assigneeHTML}</td>
        <td>${formatDate(task.exp_end_date)}</td>
        <td>${formatDate(task.modified)}</td>
      `;
      tbody.appendChild(row);
  
      // Render con
      if (task.children && task.children.length > 0) {
        for (const child of task.children) {
          await renderTaskRowRecursive(child, tbody, level + 1);
        }
      }
    }
  
    // 🔸 Hàm lấy danh sách người được giao (Assigned To)
    async function getAssignees(taskName) {
      try {
        const res = await fetch(
          `/api/resource/ToDo?fields=["allocated_to"]&filters=[["reference_name","=","${taskName}"],["status","!=","Cancelled"]]`
        );
        const json = await res.json();
        const list = json.data || [];
        return list.map((a) => a.allocated_to).filter(Boolean);
      } catch (e) {
        console.error("⚠️ Lỗi lấy assignee cho", taskName, e);
        return [];
      }
    }
  
    // 🔸 Hàm lấy tên Project
    async function getProjectName(projectId) {
      if (!projectId) return "";
      try {
        const res = await fetch(`/api/resource/Project/${projectId}?fields=["project_name"]`);
        const json = await res.json();
        return json.data?.project_name || projectId;
      } catch (e) {
        console.warn("⚠️ Lỗi lấy tên Project:", projectId, e);
        return projectId;
      }
    }
  
    // 🔸 Hàm dựng HTML avatar
    async function getUserAvatarHTML(email) {
      if (!email) return "";
      try {
        const res = await fetch(`/api/resource/User/${email}`);
        const userData = await res.json();
        const user = userData.data || {};
        const first = (user.first_name || "").trim();
        const last = (user.last_name || "").trim();
        const initials = `${first.charAt(0)}${last.charAt(0)}`.toUpperCase() || email.charAt(0).toUpperCase();
        return avatarHTML(initials, user.full_name || email);
      } catch (e) {
        const initials = email.charAt(0).toUpperCase();
        return avatarHTML(initials, email);
      }
    }
  
    function avatarHTML(initials, title) {
      return `
        <div title="${title}" style="
          width:26px;height:26px;
          border-radius:50%;
          background:#f5f5f5;
          display:inline-flex;
          align-items:center;
          justify-content:center;
          color:#333;
          font-size:11px;
          font-weight:400;
          text-transform:uppercase;
          border:1px solid #ddd;
          margin:0 2px;
        ">${initials}</div>`;
    }
  
    function formatDate(str) {
      if (!str) return "";
      const d = new Date(str);
      // Định dạng dd/mm/yyyy
      return d.toLocaleDateString("vi-VN"); 
    }
  });