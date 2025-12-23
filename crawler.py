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
    """상세 페이지 본문 추출 (다양한 선택자 적용)"""
    try:
        time.sleep(1.5)
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        for tag in soup(["script", "style", "nav", "footer", "header", "button"]):
            tag.decompose()

        # 사람인 및 일반 사이트 대응 강화된 선택자
        selectors = [
            '.user_content', '.job_detail', '.view_con', '.template_area', 
            '.recruitment_view_cont', '#content', 'main', 'article'
        ]
        
        content_text = ""
        for sel in selectors:
            target = soup.select_one(sel)
            if target:
                content_text = target.get_text(separator="\n", strip=True)
                break
        
        if not content_text or len(content_text) < 50:
            content_text = soup.body.get_text(separator="\n", strip=True) if soup.body else "내용 확인 불가"
            
        # 텍스트가 너무 길면 잘림 방지 (CSV 저장 용도)
        return content_text[:10000] 
    except Exception as e:
        return f"수집 실패: {str(e)}"

def get_bep_jobs():
    """BEP 수집 로직 - 키워드 필터링 및 리스트 추출 강화"""
    url = "https://bep.co.kr/Career/recruitment" # 전체 공고 페이지에서 필터링
    jobs = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 모든 공고 링크를 먼저 찾음
        links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for l in links:
            text = l.get_text(" ", strip=True)
            # 상태 및 키워드 검사 (전기차, 충전, 워터 등)
            if "모집중" in text and any(k in text for k in ["전기차", "충전", "워터", "WATER", "운영"]):
                href = l.get('href', '')
                full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
                title = text.replace("모집중", "").strip()
                jobs.append(['BEP', title, "공고 참조", full_link])
    except Exception as e:
        print(f"BEP 크롤링 실패: {e}")
    return jobs

def get_saramin_jobs(companies):
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.item_recruit')
            for item in items:
                co_name = item.select_one('.corp_name a').text.strip()
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    link = "https://www.saramin.co.kr" + title_tag['href']
                    jobs.append([co_name, title_tag.text.strip(), "공고 참조", link])
            time.sleep(1)
        except: continue
    return jobs

def main():
    target_companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 데이터 로드
    master_file = "job_listings_all.csv"
    comp_file = "Recruitment_completed.csv"
    ency_file = "encyclopedia.csv"

    df_master = pd.read_csv(master_file) if os.path.exists(master_file) else pd.DataFrame(columns=['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = pd.read_csv(ency_file) if os.path.exists(ency_file) else pd.DataFrame(columns=['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = pd.read_csv(comp_file) if os.path.exists(comp_file) else pd.DataFrame(columns=['company', 'title', 'experience', 'link', 'completed_date'])

    # 2. 크롤링 수행
    print("데이터 수집 중...")
    bep_data = get_bep_jobs()
    saram_data = get_saramin_jobs(target_companies)
    current_jobs = bep_data + saram_data
    df_current = pd.DataFrame(current_jobs, columns=['company', 'title', 'experience', 'link'])

    # [수정] 수집 성공 여부 확인 (안전장치)
    successful_companies = df_current['company'].unique()

    # 3. 신규 공고 처리 (Master 업데이트 및 슬랙)
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        # 슬랙 발송 로직 (생략 - 이전과 동일)
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 4. 종료 공고 처리 (안전장치 적용)
    # 수집에 성공한 회사의 공고인데, 오늘 목록에 없으면 완료된 것으로 판단
    # BEP 데이터가 0건이면 BEP 공고는 완료 처리를 하지 않고 유지함 (크롤링 오류 대비)
    is_active = df_master['link'].isin(df_current['link'])
    is_from_failed_scan = ~df_master['company'].isin(successful_companies)
    
    # 정말 종료된 것: 오늘 목록에 없고(not is_active), 해당 회사의 크롤링은 성공했을 때(not is_from_failed_scan)
    closed_entries = df_master[~is_active & ~is_from_failed_scan].copy()
    
    if not closed_entries.empty:
        closed_entries['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_entries], ignore_index=True)
        # 마스터에서 제거
        df_master = df_master[is_active | is_from_failed_scan]

    # 5. 백과사전(Encyclopedia) 업데이트 (내용 없는 건 재수집 포함)
    # 신규 링크 + 기존에 "내용 확인 불가"였던 링크들 대상
    needs_content = df_current[~df_current['link'].isin(df_ency[df_ency['content'] != "내용 확인 불가"]['link'])]
    
    if not needs_content.empty:
        print(f"상세 내용 {len(needs_content)}건 수집/갱신 중...")
        for idx, row in needs_content.iterrows():
            content = fetch_detail_content(row['link'])
            # 기존에 있으면 업데이트, 없으면 추가
            if row['link'] in df_ency['link'].values:
                df_ency.loc[df_ency['link'] == row['link'], ['content', 'last_updated']] = [content, today]
            else:
                new_row = pd.DataFrame([{'link': row['link'], 'company': row['company'], 'title': row['title'], 'content': content, 'last_updated': today}])
                df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 6. 파일 저장
    df_master.to_csv(master_file, index=False, encoding='utf-8-sig')
    df_comp.to_csv(comp_file, index=False, encoding='utf-8-sig')
    df_ency.to_csv(ency_file, index=False, encoding='utf-8-sig')
    print("저장 완료.")

if __name__ == "__main__":
    main()
