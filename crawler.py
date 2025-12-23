import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os

SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def fetch_detail_content(url):
    """상세 페이지의 본문 텍스트를 추출"""
    try:
        time.sleep(1) # 차단 방지를 위한 간격
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 불필요한 태그 제거 (스크립트, 스타일 등)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # 사이트별 주요 본문 영역 추출 (휴리스틱 방식)
        if "saramin.co.kr" in url:
            # 사람인은 보통 .user_content나 .job_detail에 내용이 있음
            content = soup.select_one('.user_content') or soup.select_one('.job_detail')
        else:
            # BEP 등 기타 사이트용
            content = soup.select_one('main') or soup.select_one('#content') or soup.body

        if content:
            # 줄바꿈과 공백 정리
            text = content.get_text(separator="\n", strip=True)
            return text
        return "본문 내용을 찾을 수 없습니다."
    except Exception as e:
        return f"수집 실패: {str(e)}"

# --- 기존 수집 함수 (get_bep_jobs, get_saramin_jobs)는 동일하게 유지 ---
# (공간 절약을 위해 함수 내부 로직은 생략하며, 이전 코드와 동일하다고 가정합니다.)

def get_bep_jobs():
    # ... (이전 코드와 동일)
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        all_links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for link_tag in all_links:
            text = link_tag.get_text(" ", strip=True)
            if "모집중" not in text: continue
            href = link_tag.get('href', '')
            full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
            title = text.replace("모집중", "").replace("전기차충전사업부문", "").strip()
            jobs.append(['BEP', title, "상세 참조", full_link])
    except: pass
    return jobs

def get_saramin_jobs(companies):
    # ... (이전 코드와 동일)
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.item_recruit')
            for item in items:
                co_tag = item.select_one('.corp_name a')
                if not co_tag: continue
                co_name = co_tag.text.strip()
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    jobs.append([co_name, title_tag.text.strip(), "상세 참조", "https://www.saramin.co.kr" + title_tag['href']])
            time.sleep(1)
        except: pass
    return jobs

def send_slack_message(new_jobs):
    if not SLACK_WEBHOOK_URL or not new_jobs: return
    message = f"📢 *신규 채용 공고 ({len(new_jobs)}건)*\n\n"
    for job in new_jobs:
        message += f"• *[{job[0]}]* {job[1]}\n  <{job[3]}|공고 보기>\n\n"
    requests.post(SLACK_WEBHOOK_URL, json={"text": message})

def main():
    saramin_target = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 목록 크롤링
    scraped_data = get_bep_jobs() + get_saramin_jobs(saramin_target)
    df_current = pd.DataFrame(scraped_data, columns=['company', 'title', 'experience', 'link'])
    
    master_file = "job_listings_all.csv"
    completed_file = "Recruitment_completed.csv"
    encyclopedia_file = "encyclopedia.csv"

    # 2. 백과사전(Encyclopedia) 로드 및 신규 내용 수집
    if os.path.exists(encyclopedia_file):
        df_encyclopedia = pd.read_csv(encyclopedia_file)
    else:
        df_encyclopedia = pd.DataFrame(columns=['link', 'company', 'title', 'content', 'last_updated'])

    # 아직 백과사전에 없는 링크들만 필터링
    new_links_to_fetch = df_current[~df_current['link'].isin(df_encyclopedia['link'])]

    if not new_links_to_fetch.empty:
        print(f"{len(new_links_to_fetch)}개의 새로운 상세 내용 수집 시작...")
        new_details = []
        for _, row in new_links_to_fetch.iterrows():
            content = fetch_detail_content(row['link'])
            new_details.append({
                'link': row['link'],
                'company': row['company'],
                'title': row['title'],
                'content': content,
                'last_updated': today_str
            })
        
        # 새로운 상세 내용을 백과사전에 추가
        df_new_ency = pd.DataFrame(new_details)
        df_encyclopedia = pd.concat([df_encyclopedia, df_new_ency], ignore_index=True)
        df_encyclopedia.to_csv(encyclopedia_file, index=False, encoding='utf-8-sig')

    # 3. 기존 마스터/완료 로직 (동일하게 작동)
    if os.path.exists(master_file):
        df_master = pd.read_csv(master_file)
    else:
        df_master = pd.DataFrame(columns=['company', 'title', 'experience', 'link', 'first_seen'])

    df_new_jobs = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not df_new_jobs.empty:
        df_new_jobs['first_seen'] = today_str
        send_slack_message(df_new_jobs.values.tolist())
    
    df_closed = df_master[~df_master['link'].isin(df_current['link'])].copy()
    if not df_closed.empty:
        df_closed['completed_date'] = today_str
        if os.path.exists(completed_file):
            df_comp_history = pd.read_csv(completed_file)
            df_comp_history = pd.concat([df_comp_history, df_closed], ignore_index=True)
        else:
            df_comp_history = df_closed
        df_comp_history.to_csv(completed_file, index=False, encoding='utf-8-sig')

    df_still_active = df_master[df_master['link'].isin(df_current['link'])]
    df_final_master = pd.concat([df_still_active, df_new_jobs], ignore_index=True)
    df_final_master.to_csv(master_file, index=False, encoding='utf-8-sig')
    
    print("모든 작업 완료!")

if __name__ == "__main__":
    main()
