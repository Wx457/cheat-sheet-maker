// content.js

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// ============================================================
// Locate scroll container → scroll & capture → deduplicate
// ============================================================
async function scrollAndCollect() {
  const scrollableDiv = document.querySelector('[data-scroll-root]');

  if (!scrollableDiv) {
    console.error("Cannot find data-scroll-root container, unable to auto-scroll!");
    return extractCurrentView();
  }

  console.log("Found scroll container:", scrollableDiv);
  console.log("Starting stream capture...");

  let uniqueTexts = new Set();
  let orderedContent = [];

  // Scroll to top first; use 'instant' to avoid smooth-scroll delay
  scrollableDiv.scrollTo({ top: 0, behavior: "instant" });
  await sleep(1000);

  let lastScrollTop = -1;
  const step = 600;
  
  while (true) {
    // Capture all visible conversation fragments
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

    // Check if bottom is reached
    const isAtBottom = Math.ceil(scrollableDiv.scrollTop + scrollableDiv.clientHeight) >= scrollableDiv.scrollHeight - 50;
    
    if (isAtBottom) {
      console.log("Reached page bottom");
      break;
    }
    
    // Deadlock detection: position unchanged means stuck
    if (Math.abs(scrollableDiv.scrollTop - lastScrollTop) < 5 && lastScrollTop !== -1) {
        console.warn("Scroll position unchanged, attempting forced scroll...");
        scrollableDiv.scrollBy({ top: step, behavior: "instant" });
        await sleep(500);
        if (Math.abs(scrollableDiv.scrollTop - lastScrollTop) < 5) {
             console.log("Scroll completely stuck, ending capture");
             break;
        }
    }
    lastScrollTop = scrollableDiv.scrollTop;

    scrollableDiv.scrollBy({ top: step, behavior: "instant" });
    
    // Wait for lazy-loaded content (increase to 800–1000 on slow networks)
    await sleep(600); 
  }

  const finalTitle = document.title || window.location.href;
  
  if (orderedContent.length === 0) {
      return extractCurrentView();
  }

  let combinedText = orderedContent.map((text, index) => {
      return `=== Conversation Fragment ${index + 1} ===\n\n${text}`;
  }).join("\n\n");

  console.log(`Capture completed, collected ${orderedContent.length} fragments`);
  
  return {
    title: finalTitle,
    text: combinedText
  };
}

// Fallback: grab whatever is currently visible
function extractCurrentView() {
    const divs = document.querySelectorAll('.markdown');
    let text = "";
    divs.forEach((div, i) => {
        text += `=== Fragment ${i+1} ===\n${div.innerText.trim()}\n\n`;
    });
    return {
        title: document.title,
        text: text || document.body.innerText
    };
}

// Message listener
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrape') {
    (async () => {
      try {
        const data = await scrollAndCollect();
        if (!data.text || data.text.length < 5) {
             throw new Error("Captured content is empty");
        }
        sendResponse({ success: true, text: data.text, title: data.title });
      } catch (error) {
        console.error("Capture process error:", error);
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true; 
  }
});
