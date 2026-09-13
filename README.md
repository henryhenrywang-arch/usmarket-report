# 每日市場觀察

比照你截圖那個報告排版重做的版本：指數、公債殖利率曲線、CPI／就業數據、
FOMC 行事曆、Fed 政策路徑機率、觀察門檻、資料來源，一次全包。純靜態網站，
GitHub Actions 每天收盤後自動更新一次。

## 跟原本的「即時儀表板」差在哪

| | 儀表板版 | 報告版（這次） |
|---|---|---|
| 內容 | 即時報價＋走勢圖 | 完整盤後彙整＋文字解讀 |
| 資料 | 只有價格 | 價格＋殖利率曲線＋CPI／就業＋FOMC 機率 |
| 文字 | 無 | 每段附一句 AI 生成的解讀（可關閉） |
| 歷史 | 無 | 有「歷史查詢」可回顧過去每一天的報告 |

## 建置步驟

1. 建一個新 repo，把這個資料夾內容全部推上去（記得檢查 `.github` 資料夾有沒有一起上傳，
   Finder／檔案總管預設會把它隱藏，用網頁版上傳最保險）。
2. Settings → Pages → Source 選 **Deploy from a branch**，分支 `main`、資料夾 `/ (root)`。
3. Settings → Actions → General → Workflow permissions 選 **Read and write permissions**。
4.（可選但強烈建議）Settings → Secrets and variables → Actions → New repository secret：
   - Name：`ANTHROPIC_API_KEY`
   - Value：你的 Anthropic API key（[console.anthropic.com](https://console.anthropic.com) 申請）

   沒設定這把 key 也能跑，只是每個區塊底下的「一句話解讀」會是空的，數字本身照樣正常更新。
5. Actions → **Refresh market report** → Run workflow，跑第一次產生資料。
6. 打開 `https://<你的帳號>.github.io/<repo 名稱>/`。

## 資料怎麼來的（誠實說明各項限制）

- **指數、VIX、商品、DXY、聯邦基金期貨**：Yahoo Finance（yfinance），免費無需 key。
- **公債殖利率、CPI、初領失業救濟金、Fed 目標利率區間**：FRED 的公開 CSV 端點，一樣免 key。
- **Fed 政策路徑（第五節）**：CME 官方 FedWatch 的資料是他們自家系統算的，沒有公開 API。
  這裡改用「30 天期聯邦基金期貨定價」自己算一個概略的升息機率，方法相近但**不是**
  CME 官方數字，頁面上會註明這件事。
- **FOMC 會議日期**（第四節）：直接寫死在 `scripts/build_data.py` 的 `FOMC_MEETINGS_2026`
  清單裡，來自 federalreserve.gov 公告的行事曆。每年年底記得手動更新成下一年的日期。
- **文字解讀**：如果有設定 `ANTHROPIC_API_KEY`，腳本會把當天算好的數字丟給 Claude，
  請它針對每一段寫一句 30 字以內的中性解讀（不給投資建議）。沒設定的話這欄就留空。
- **後續觀察重點（第六節）門檻表**：目前是固定的參考門檻（10Y 站上 5%、2s10s 倒掛等），
  不是每天算出來的，想改成動態判斷可以在 `build_data.py` 裡加邏輯。

## 本機預覽

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # 可省略
python scripts/build_data.py
python -m http.server 8000            # 開 http://localhost:8000
```

## 想改什麼

- 顏色配置：`index.html` 最上面 `:root` 那組 CSS 變數，`--up`/`--down` 決定漲跌顏色
  （這版預設紅漲綠跌，符合台灣習慣）。
- 加更多指標：在 `build_data.py` 對應的 `build_xxx()` 函式裡加代號即可。
- 深色模式、列印、另存 HTML、歷史查詢按鈕都已經接好，不用額外設定。

資料延遲且僅供參考，不構成投資建議。
