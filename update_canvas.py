import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

# 1. 환경 변수 및 설정
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_PATH = "job_listings_all.csv"
CSV_PATH_2 = "encyclopedia.csv"

# [수정] 본인의 GitHub 정보를 입력하세요
GITHUB_USER = "ian939"
GITHUB_REPO = "HR-crawler"
# 최신 파일을 바로 다운로드할 수 있는 주소입니다.
DOWNLOAD_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/raw/main/{CSV_PATH_2}"

def update_slack_canvas():
    if not SLACK_TOKEN or not CANVAS_ID: return
    client = WebClient(token=SLACK_TOKEN)

    try:
        if not os.path.exists(CSV_PATH): return
        df = pd.read_csv(CSV_PATH)
        df = df.sort_values(by='first_seen', ascending=False)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # --- 캔버스 마크다운 구성 ---
        markdown_text = f"# 🚀 채용 정보 리스트 ({today})\n\n"
        
        # [추가] 다운로드 섹션 - 버튼처럼 보이게 구성
        markdown_text += "### 📥 데이터 보관함\n"
        markdown_text += f"> [**💾 최신 CSV 파일 다운로드 (GitHub)**]({DOWNLOAD_URL})\n"
        markdown_text += "*위 링크를 클릭하면 현재 리포지토리에 저장된 전체 원본 파일을 받을 수 있습니다.*\n\n"
        
        markdown_text += "---\n\n"
        
        # 표 헤더 (이전의 너비 최적화 적용)
        markdown_text += "| 회사명 | 공고 제목" + "　" * 25 + " | 경력 | 등록일 | 🔗 |\n"
        markdown_text += "|:---|:---|:---|:---|:---:|\n"
        
        for _, row in df.head(40).iterrows():
            title = row['title'][:45] + ".." if len(row['title']) > 45 else row['title']
            markdown_text += (
                f"| {row['company']} | {title} | {row['experience']} | {row['first_seen']} | [🔗]({row['link']}) |\n"
            )
            
        markdown_text += f"\n\n---\n*최종 동기화: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

        # 캔버스 전송
        client.canvases_edit(
            canvas_id=CANVAS_ID,
            changes=[{"operation": "replace", "document_content": {"type": "markdown", "markdown": markdown_text}}]
        )
        print("✅ 다운로드 링크를 포함하여 업데이트 성공!")

    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    update_slack_canvas()
