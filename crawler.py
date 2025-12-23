import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def fetch_detail_content(url):
    """상세 페이지 본문 추출 (사람인 특수 주소 대응 및 노이즈 필터링)"""
    try:
        time.sleep(2)
        target_url = url
        
        # [사람인 전용] 상세 요강이 들어있는 실제 데이터 URL로 우회 (로그인/요약문구 회피)
        if "saramin.co.kr" in url and "rec_idx=" in url:
            rec_idx_match = re.search(r'rec_idx=(\d+)', url)
            if rec_idx_match:
                # view-detail 주소가 실제 텍스트 내용을 담고 있는 경우가 많음
                target_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec_idx_match.group(1)}"

        res = requests.get(target_url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 불필요한 태그 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside"]):
            tag.decompose()

        # 본문이 위치하는 주요 클래스들 (에버온처럼 긴 텍스트를 가진 영역 찾기)
        selectors = [
            '.user_content',        # 사람인 본문 영역
            '.recruit_view_cont',   # BEP 본문 영역
            '.view_con',            # 일반적인 본문 1
            '.job_detail',          # 일반적인 본문 2
            '.template_area',       # 사람인 템플릿 영역
            '#content'              # 기본 아이디
        ]
        
        content_text = ""
        for sel in selectors:
            target = soup.select_one(sel)
            if target:
                candidate = target.get_text(separator="\n", strip=True)
                # "채용공고 상세" 같은 짧은 문구는 무시하고 의미 있는 길이(50자 이상)만 선택
                if len(candidate) > 50 and "채용공고 상세" not in candidate[:15]:
                    content_text = candidate
                    break
        
        # 여전히 내용을 못 찾았다면, 가장 텍스트가 많은 영역을 추출 시도
        if len(content_text) < 100:
            all_text = soup.get_text(separator="\n", strip=True)
            # 로그인 관련 노이즈 제거
            if "로그인" in all_text[:200] and len(all_text) < 500:
                return "본문 내용 확인 불가 (상세 페이지 링크 참조)"
            content_text = all_text

        return content_text[:20000] # CSV 저장 한계 고려
    except Exception as e:
        return f"수집 실패: {str(e)}"

def get_bep_jobs():
    """BEP 수집 로직 - 워터(전기차충전사업부문) 전용 페이지 크롤링"""
    # 사용자가 지정한 type=3 (전기차충전사업부문) 필터 적용 URL
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # BEP 채용 목록 링크 추출
        links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for l in links:
            title = l.get_text(" ", strip=True)
            # 목록 이동 버튼 등 불필요한 링크 제외
            if not title or "목록" in title: continue
            
            href = l.get('href', '')
            full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
            
            # 제목에서 '모집중' 키워드 제거
            clean_title = title.replace("모집중", "").strip()
            
            # 이 페이지는 이미 필터링된 페이지이므로 바로 추가
            jobs.append(['BEP(워터)', clean_title, "공고 참조", full_link])
    except Exception as e:
        print(f"BEP 크롤링 실패: {e}")
    return jobs

def get_saramin_jobs(companies):
    """사람인 기업 검색 및 리스트 추출"""
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
                # 기업명 필터링 (주식회사 등 제외 매칭)
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    link = "https://www.saramin.co.kr" + title_tag['href']
                    jobs.append([co_name, title_tag.text.strip(), "공고 참조", link])
            time.sleep(1.5)
        except: continue
    return jobs

def safe_load_df(file_path, default_cols):
    """파일 로드 시 컬럼명 정제 로직"""
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            for col in default_cols:
                if col not in df.columns: df[col] = ""
            return df[default_cols]
        except:
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def main():
    saramin_targets = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 데이터 로드
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date'])

    print(f"[{today}] 데이터 수집 시작...")
    
    # 1. 수집 수행 (BEP는 특정 URL 사용)
    current_jobs = get_bep_jobs() + get_saramin_jobs(saramin_targets)
    df_current = pd.DataFrame(current_jobs, columns=['company', 'title', 'experience', 'link'])

    if df_current.empty:
        print("수집된 데이터가 없습니다.")
        return

    # 2. 신규 공고 알림 및 마스터 업데이트
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        if SLACK_WEBHOOK_URL:
            msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
            for _, r in new_entries.iterrows(): msg += f"• [{r['company']}] {r['title']}\n  <{r['link']}|공고 보기>\n"
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 3. 채용 종료 처리
    successful_scan_cos = df_current['company'].unique()
    is_missing = ~df_master['link'].isin(df_current['link'])
    is_safe = df_master['company'].isin(successful_scan_cos)
    closed_entries = df_master[is_missing & is_safe].copy()
    if not closed_entries.empty:
        closed_entries['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_entries], ignore_index=True)
        df_master = df_master[~(is_missing & is_safe)]

    # 4. 백과사전(Encyclopedia) 본문 수집
    # 대상: 백과사전에 아예 없거나, 기존 내용이 '채용공고 상세' 또는 부실한 경우
    retry_keywords = ["채용공고 상세", "본문 내용을 찾을 수 없습니다", "로그인", "확인 불가", "링크 참조"]
    is_poor_content = df_ency['content'].apply(lambda x: any(k in str(x) for k in retry_keywords) or len(str(x)) < 100)
    
    retry_links = df_ency[is_poor_content]['link'].tolist() if not df_ency.empty else []
    add_links = df_current[~df_current['link'].isin(df_ency['link'])]['link'].tolist()
    target_links = list(set(retry_links + add_links))

    if target_links:
        print(f"상세 본문 {len(target_links)}건 수집/갱신 중...")
        for link in target_links:
            source = df_current[df_current['link'] == link]
            if source.empty: source = df_master[df_master['link'] == link]
            if source.empty: continue
            
            row = source.iloc[0]
            content = fetch_detail_content(link)
            
            if link in df_ency['link'].values:
                df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            else:
                new_row = pd.DataFrame([{'link': link, 'company': row['company'], 'title': row['title'], 'content': content, 'last_updated': today}])
                df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 파일 저장
    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    print("성공적으로 작업을 마쳤습니다.")

if __name__ == "__main__":
    main()
