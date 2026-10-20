// Клик по значку расширения открывает боковую панель с сервисом.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
