import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

# 1. 환경 변수 및 설정
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_PATH = "job_listings_all.csv"  # 실제 파일명 확인!

# GitHub 정보 (본인 계정에 맞게 확인)
GITHUB_USER = "ian939"
GITHUB_REPO = "HR-crawler"

# [수정된 다운로드 주소] - 파일명을 문자열로 정확히 넣었습니다.
DOWNLOAD_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/raw/main/{CSV_PATH}"

def update_slack_canvas():
    if not SLACK_TOKEN or not CANVAS_ID: return
    client = WebClient(token=SLACK_TOKEN)

    try:
        # 2. 데이터 확인 (안전장치)
        if not os.path.exists(CSV_PATH):
            print("❌ CSV 파일을 찾을 수 없어 업데이트를 중단합니다.")
            return
            
        df = pd.read_csv(CSV_PATH)
        
        # 데이터가 비어있으면 캔버스를 지우지 않도록 중단
        if df.empty:
            print("⚠️ 데이터가 비어있습니다. 기존 캔버스를 유지합니다.")
            return

        df = df.sort_values(by='first_seen', ascending=False)
        today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 3. 캔버스 마크다운 구성
        markdown_text = f"# 🚀 실시간 채용 리포트\n\n"
        markdown_text += "### 📥 데이터 다운로드\n"
        markdown_text += f"> [**💾 최신 CSV 파일 다운로드**]({DOWNLOAD_URL})\n"
        markdown_text += f"*최종 업데이트: {today}*\n\n---\n\n"
        
        # 표 구성 (너비 최적화 적용)
        markdown_text += "| 회사명 | 공고 제목" + "　" * 25 + " | 경력 | 등록일 | 🔗 |\n"
        markdown_text += "|:---|:---|:---|:---|:---:|\n"
        
        # 상위 40개 데이터만 노출
        for _, row in df.head(40).iterrows():
            title = str(row['title'])[:45] + ".." if len(str(row['title'])) > 45 else row['title']
            markdown_text += (
                f"| {row['company']} | {title} | {row['experience']} | {row['first_seen']} | [🔗]({row['link']}) |\n"
            )

        # 4. 캔버스 전송
        response = client.canvases_edit(
            canvas_id=CANVAS_ID,
            changes=[{
                "operation": "replace",
                "document_content": {
                    "type": "markdown",
                    "markdown": markdown_text
                }
            }]
        )
        
        if response["ok"]:
            print(f"✅ 업데이트 성공 ({today})")
        else:
            print(f"❌ API 에러: {response['error']}")

    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    update_slack_canvas()
