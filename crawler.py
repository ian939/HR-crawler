import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os
from urllib.parse import urljoin, urlparse, parse_qs

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def safe_load_df(file_path, default_cols):
    """파일 로드 시 컬럼 보장 및 중복/공백 제거"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip')
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            # link 컬럼 데이터 정제 및 중복 제거
            if 'link' in df.columns:
                df['link'] = df['link'].astype(str).str.strip()
                df = df.drop_duplicates(subset=['link'], keep='first')
            # 없는 컬럼 생성
            for col in default_cols:
                if col not in df.columns: 
                    df[col] = "" if col not in ['first_seen', 'completed_date', 'last_updated'] else None
            return df[default_cols]
        except Exception as e:
            print(f"로드 실패({file_path}): {e}")
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def is_invalid_content(text):
    """유효하지 않은 content 판별"""
    if not text or len(text) < 50:
        return True
    
    invalid_keywords = [
        "로그인이 필요한",
        "로그인 유지",
        "아이디 비밀번호",
        "회원가입",
        "본문 바로가기",
        "검색 폼",
        "개인정보 보호",
        "소셜 계정으로",
        "채용과정에서 수집된"
    ]
    
    # 3개 이상의 키워드가 있으면 로그인 페이지로 판단
    keyword_count = sum(1 for kw in invalid_keywords if kw in text)
    if keyword_count >= 3:
        return True
    
    return False

def extract_saramin_detail(url):
    """사람인 상세 내용 추출 (개선 버전)"""
    try:
        # rec_idx 추출
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        rec_idx = params.get('rec_idx', [None])[0]
        
        if not rec_idx:
            return "링크 오류"
        
        # 직접 상세 페이지로 접근
        detail_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}"
        
        session = requests.Session()
        session.headers.update(HEADERS)
        
        time.sleep(1)
        res = session.get(detail_url, timeout=15, allow_redirects=True)
        
        # 로그인 페이지로 리다이렉트되었는지 확인
        if 'member/login' in res.url or res.status_code != 200:
            print(f"    ⚠️  로그인 필요 - 이미지 공고 탐색")
            # 검색 결과 페이지에서 이미지 추출 시도
            return extract_image_from_search(url)
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 불필요 요소 제거
        for tag in soup.select('script, style, nav, footer, header, .btn_area, .login_wrap, #gfm_frame'):
            tag.decompose()
        
        # 1순위: 채용 공고 본문
        content_selectors = [
            '.user_content',
            '.jobcont_wrap',
            '.jv_cont',
            '#content',
            '.recruit_contents'
        ]
        
        for selector in content_selectors:
            content_area = soup.select_one(selector)
            if content_area:
                # 텍스트 추출
                text = content_area.get_text(separator="\n", strip=True)
                
                # 유효성 검사
                if not is_invalid_content(text) and len(text) > 100:
                    # 연속 공백 및 줄바꿈 정리
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    text = re.sub(r' {2,}', ' ', text)
                    return text[:15000]
        
        # 2순위: 이미지 공고 추출
        return extract_image_from_search(url)
        
    except Exception as e:
        print(f"    ✗ 추출 실패: {e}")
        return extract_image_from_search(url)

def extract_image_from_search(url):
    """검색 결과 페이지에서 이미지 URL 추출"""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        rec_idx = params.get('rec_idx', [None])[0]
        searchword = params.get('searchword', [''])[0]
        
        if not rec_idx:
            return "이미지 추출 실패"
        
        # 검색 페이지 접근
        search_url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={searchword}"
        
        time.sleep(0.5)
        res = requests.get(search_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 해당 rec_idx를 가진 항목 찾기
        for item in soup.select('.item_recruit'):
            link_tag = item.select_one('.job_tit a')
            if link_tag and rec_idx in link_tag.get('href', ''):
                # 이미지 태그 찾기
                img_tag = item.select_one('.logo img, .thumb img, img')
                if img_tag:
                    img_src = img_tag.get('src') or img_tag.get('data-src')
                    if img_src and 'recruit' in img_src:
                        return f"[이미지 공고] {img_src}"
        
        # 직접 접근 시도
        detail_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}"
        res = requests.get(detail_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        imgs = soup.select('.user_content img, .jobcont_wrap img')
        recruit_imgs = [img.get('src') or img.get('data-src') for img in imgs 
                       if img.get('src') and 'recruit' in img.get('src', '')]
        
        if recruit_imgs:
            return "[이미지 공고] " + ", ".join(recruit_imgs[:2])
        
        return "상세 링크 참조"
        
    except:
        return "이미지 추출 실패"

def fetch_detail_content(url):
    """상세 본문 추출 (사이트별 분기)"""
    try:
        # 사람인
        if 'saramin.co.kr' in url:
            return extract_saramin_detail(url)
        
        # BEP 또는 기타
        time.sleep(1)
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 불필요 태그 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "button"]): 
            tag.decompose()

        # 본문 영역 탐색
        content_area = soup.select_one('.user_content, .recruit_view_cont, .view_con, .job_detail, .content, body')
        text_content = content_area.get_text(separator="\n", strip=True) if content_area else ""
        
        # 유효성 검사
        if is_invalid_content(text_content):
            text_content = ""
        
        # 텍스트가 부족하면 이미지 수집
        if len(text_content) < 150 and content_area:
            imgs = content_area.find_all('img')
            img_urls = [urljoin(url, i.get('src') or i.get('data-src')) 
                       for i in imgs if i.get('src') or i.get('data-src')]
            clean_imgs = [i for i in img_urls 
                         if not any(x in i.lower() for x in ["icon", "logo", "common", "header"])]
            
            if clean_imgs: 
                return "[이미지 공고] " + ", ".join(clean_imgs[:3])

        return text_content[:15000] if len(text_content) > 50 else "상세 링크 참조"
        
    except Exception as e:
        print(f"    [상세수집 실패] {str(e)[:50]}")
        return "수집 실패"

def get_bep_jobs():
    """BEP(워터) 수집: Selenium 없이 최대한 우회"""
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    
    try:
        print("  [BEP 수집 시작]")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://bep.co.kr/Career',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        
        # 메인 페이지 먼저 방문 (쿠키 획득)
        session.get('https://bep.co.kr/', timeout=10)
        time.sleep(1)
        
        # 채용 페이지 접근
        res = session.get(url, timeout=20)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        print(f"  [응답코드] {res.status_code}")
        
        # 전략 1: 테이블 구조 탐색
        table = soup.find('table') or soup.find('tbody')
        if table:
            rows = table.find_all('tr')
            print(f"  [테이블] {len(rows)}개 행 발견")
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                # 링크 찾기
                link_tag = row.find('a', href=True)
                if not link_tag:
                    continue
                
                href = link_tag.get('href', '').strip()
                if not href or href in ['#', 'javascript:void(0)']:
                    continue
                
                # 텍스트 추출
                title_text = link_tag.get_text(strip=True)
                
                # 상태 확인 (모집중인지)
                row_text = row.get_text()
                if "마감" in row_text or "종료" in row_text:
                    continue
                
                # 필터링
                if not title_text or len(title_text) < 3:
                    continue
                if title_text in ["목록", "이전", "다음", "HOME"]:
                    continue
                
                full_link = urljoin("https://bep.co.kr", href)
                
                # 중복 체크
                if any(j[3] == full_link for j in jobs):
                    continue
                
                print(f"    ✓ {title_text}")
                jobs.append(['BEP(워터)', title_text, "공고 확인", full_link])
        
        # 전략 2: 리스트 구조
        if not jobs:
            items = soup.select('.recruit_list li, .list_item, .recruitment_item')
            print(f"  [리스트] {len(items)}개 항목 탐색")
            
            for item in items:
                link_tag = item.find('a', href=True)
                if not link_tag:
                    continue
                
                href = link_tag.get('href', '').strip()
                title = link_tag.get_text(strip=True)
                
                if href and title and len(title) > 3:
                    full_link = urljoin("https://bep.co.kr", href)
                    if not any(j[3] == full_link for j in jobs):
                        jobs.append(['BEP(워터)', title, "공고 확인", full_link])
        
        # 전략 3: recruitmentView 직접 검색
        if not jobs:
            all_links = soup.find_all('a', href=re.compile(r'recruitment'))
            print(f"  [전체링크] {len(all_links)}개 필터링")
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if 'view' in href.lower() and len(text) > 3:
                    if text not in ["목록", "이전", "다음"]:
                        full_link = urljoin("https://bep.co.kr", href)
                        if not any(j[3] == full_link for j in jobs):
                            jobs.append(['BEP(워터)', text, "공고 확인", full_link])
        
        print(f"  [BEP 완료] {len(jobs)}건 수집")
        
        # 수집 실패 시 직접 링크 추가 (알려진 공고가 있다면)
        if not jobs:
            print("  ⚠️  자동 수집 실패 - 수동 확인 필요")
        
    except Exception as e:
        print(f"  [BEP 오류] {e}")
    
    return jobs

def get_saramin_jobs(companies):
    """사람인 수집"""
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    
    for company in companies:
        try:
            print(f"  [사람인] {company} 검색 중...")
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            count = 0
            for item in soup.select('.item_recruit'):
                co_tag = item.select_one('.corp_name a')
                if co_tag and company in co_tag.text.replace(" ", ""):
                    title_tag = item.select_one('.job_tit a')
                    conds = item.select('.job_condition span')
                    exp = conds[1].text.strip() if len(conds) > 1 else "경력무관"
                    
                    link = "https://www.saramin.co.kr" + title_tag['href']
                    jobs.append([co_tag.text.strip(), title_tag.text.strip(), exp, link])
                    count += 1
            
            print(f"    ✓ {count}건 발견")
            time.sleep(1)
            
        except Exception as e:
            print(f"    ✗ 오류: {e}")
            continue
    
    return jobs

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 기존 데이터 로드
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'first_seen', 'completed_date', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date', 'first_seen'])

    print(f"\n{'='*60}")
    print(f"[{today}] 채용공고 수집 시작")
    print(f"{'='*60}\n")
    
    # 2. 크롤링 실행
    targets = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    
    bep_jobs = get_bep_jobs()
    saramin_jobs = get_saramin_jobs(targets)
    
    scraped_data = bep_jobs + saramin_jobs
    
    if not scraped_data:
        print("\n⚠️  수집된 공고가 없습니다.")
        return
    
    df_current = pd.DataFrame(scraped_data, columns=['company', 'title', 'experience', 'link'])
    df_current['link'] = df_current['link'].str.strip()
    df_current = df_current.drop_duplicates(subset=['link'])
    
    print(f"\n📊 수집 결과: 총 {len(df_current)}건")

    # 3. 신규 공고 처리
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    
    if not new_entries.empty:
        print(f"\n🆕 신규 공고 {len(new_entries)}건 발견!")
        new_entries['first_seen'] = today
        
        if SLACK_WEBHOOK_URL:
            msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
            for _, r in new_entries.iterrows():
                msg += f"• [{r['company']}] {r['title']}\n  <{r['link']}|보기>\n"
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        
        df_master = pd.concat([df_master, new_entries], ignore_index=True)
    else:
        print("\n✅ 신규 공고 없음")

    # 4. 종료 공고 처리
    active_links = df_current['link'].tolist()
    successfully_scraped_companies = df_current['company'].unique()
    
    is_missing = ~df_master['link'].isin(active_links)
    is_target_company = df_master['company'].isin(successfully_scraped_companies)
    
    closed_jobs = df_master[is_missing & is_target_company].copy()
    
    if not closed_jobs.empty:
        print(f"\n🔚 종료된 공고 {len(closed_jobs)}건 처리")
        closed_jobs['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_jobs], ignore_index=True)
        df_master = df_master[~(is_missing & is_target_company)]

    # 5. Encyclopedia 업데이트
    print(f"\n📚 백과사전 업데이트 중...")
    
    # 5-1. 신규 링크 추가
    new_for_ency = df_master[~df_master['link'].isin(df_ency['link'])].copy()
    
    if not new_for_ency.empty:
        print(f"  • 신규 엔트리 {len(new_for_ency)}건 추가")
        for _, row in new_for_ency.iterrows():
            new_row = pd.DataFrame([{
                'link': row['link'],
                'company': row['company'],
                'title': row['title'],
                'content': '',
                'first_seen': row['first_seen'],
                'completed_date': None,
                'last_updated': None
            }])
            df_ency = pd.concat([df_ency, new_row], ignore_index=True)
    
    # 5-2. 종료 공고 날짜 기록
    closed_links = closed_jobs['link'].tolist() if not closed_jobs.empty else []
    if closed_links:
        print(f"  • 종료 공고 {len(closed_links)}건 날짜 기록")
        df_ency.loc[df_ency['link'].isin(closed_links), 'completed_date'] = today
    
    # 5-3. Content 수집 (무효한 content 재수집)
    needs_update = (
        (df_ency['content'].isna()) | 
        (df_ency['content'] == '') |
        (df_ency['content'].str.len() < 100) |
        (df_ency['content'].str.contains('로그인이 필요한|수집 실패|이미지 추출 실패', na=False)) |
        (df_ency['content'].apply(lambda x: is_invalid_content(str(x))))
    )
    
    # 활성 공고만 수집
    active_and_needs = df_ency[needs_update & df_ency['link'].isin(active_links)]
    
    if not active_and_needs.empty:
        print(f"  • 상세 내용 수집 대상: {len(active_and_needs)}건")
        
        for idx, row in active_and_needs.iterrows():
            link = row['link']
            print(f"    [{list(active_and_needs.index).index(idx)+1}/{len(active_and_needs)}] {row['company']} - {row['title'][:30]}")
            
            content = fetch_detail_content(link)
            
            # 재검증
            if is_invalid_content(content):
                content = "상세 링크 참조"
            
            df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            time.sleep(1)  # 서버 부하 방지

    # 6. 최종 저장
    print(f"\n💾 파일 저장 중...")
    
    for df in [df_master, df_comp, df_ency]:
        if 'link' in df.columns:
            df['link'] = df['link'].astype(str).str.strip()
            df.drop_duplicates(subset=['link'], keep='first', inplace=True)

    # 정렬
    if 'company' in df_ency.columns and 'first_seen' in df_ency.columns:
        df_ency = df_ency.sort_values(by=['company', 'first_seen'], ascending=[False, False])

    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    
    print(f"\n{'='*60}")
    print(f"✅ 작업 완료!")
    print(f"  • 현재 공고: {len(df_master)}건")
    print(f"  • 종료 공고: {len(df_comp)}건")
    print(f"  • 백과사전: {len(df_ency)}건")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
