// content.js

// 辅助函数：暂停等待
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// ============================================================
// 核心逻辑：精准定位滚动条 -> 边滚边抓 -> 去重
// ============================================================
async function scrollAndCollect() {
  // 1. 【关键修复】使用你发现的 data-scroll-root 属性精准定位
  const scrollableDiv = document.querySelector('[data-scroll-root="true"]');

  if (!scrollableDiv) {
    console.error("依然未找到 data-scroll-root 容器，无法自动滚动！");
    // 如果找不到，只能兜底抓当前屏幕
    return extractCurrentView();
  }

  console.log("找到滚动容器:", scrollableDiv);
  console.log("开始流式抓取...");

  // 用于存储抓取到的所有文本，使用 Set 防止重复
  let uniqueTexts = new Set();
  let orderedContent = []; 

  // A. 先滚回顶部，确保从头开始
  // 使用 'instant' 行为防止平滑滚动拖慢节奏
  scrollableDiv.scrollTo({ top: 0, behavior: "instant" });
  await sleep(1000); // 顶部加载通常需要久一点

  // B. 开始向下滚动循环
  let lastScrollTop = -1;
  const step = 600; // 步长调小一点，确保不漏
  
  while (true) {
    // 1. 抓取当前视口可见的所有对话
    const visibleDivs = document.querySelectorAll('.markdown');
    
    if (visibleDivs.length > 0) {
        visibleDivs.forEach(div => {
          const text = div.innerText.trim();
          if (text.length > 0 && !uniqueTexts.has(text)) {
            uniqueTexts.add(text);
            orderedContent.push(text);
          }
        });
    }

    // 2. 检查是否到底
    // scrollHeight 是总高度，scrollTop 是卷去的高度，clientHeight 是可见窗口高度
    const isAtBottom = Math.ceil(scrollableDiv.scrollTop + scrollableDiv.clientHeight) >= scrollableDiv.scrollHeight - 50;
    
    if (isAtBottom) {
      console.log("已到达页面底部");
      break;
    }
    
    // 防死循环检测：位置没变说明卡住了
    if (Math.abs(scrollableDiv.scrollTop - lastScrollTop) < 5 && lastScrollTop !== -1) {
        console.warn("滚动条位置未变化，尝试强制滚动...");
        // 尝试一次大跳跃，如果还不行就退出
        scrollableDiv.scrollBy({ top: step, behavior: "instant" });
        await sleep(500);
        if (Math.abs(scrollableDiv.scrollTop - lastScrollTop) < 5) {
             console.log("滚动条彻底卡住，结束抓取");
             break;
        }
    }
    lastScrollTop = scrollableDiv.scrollTop;

    // 3. 执行向下滚动
    scrollableDiv.scrollBy({ top: step, behavior: "instant" });
    
    // 4. 等待加载 (如果你网络慢，把这里改成 800 或 1000)
    await sleep(600); 
  }

  // C. 拼接结果
  const finalTitle = document.title || window.location.href;
  
  if (orderedContent.length === 0) {
      return extractCurrentView();
  }

  // 格式化输出
  let combinedText = orderedContent.map((text, index) => {
      return `=== 对话片段 ${index + 1} ===\n\n${text}`;
  }).join("\n\n");

  console.log(`抓取完成，共收集 ${orderedContent.length} 个片段`);
  
  return {
    title: finalTitle,
    text: combinedText
  };
}

// 兜底函数
function extractCurrentView() {
    const divs = document.querySelectorAll('.markdown');
    let text = "";
    divs.forEach((div, i) => {
        text += `=== 片段 ${i+1} ===\n${div.innerText.trim()}\n\n`;
    });
    return {
        title: document.title,
        text: text || document.body.innerText
    };
}

// 监听消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrape') {
    (async () => {
      try {
        const data = await scrollAndCollect();
        if (!data.text || data.text.length < 5) {
             throw new Error("抓取内容为空");
        }
        sendResponse({ success: true, text: data.text, title: data.title });
      } catch (error) {
        console.error("抓取流程出错:", error);
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true; 
  }
});