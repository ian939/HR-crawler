import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os
from urllib.parse import urljoin

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://bep.co.kr/',
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
                    df[col] = "" if col not in ['first_seen', 'completed_date'] else None
            return df[default_cols]
        except Exception as e:
            print(f"로드 실패({file_path}): {e}")
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def fetch_detail_content(url):
    """상세 본문 추출 (텍스트 우선, 부족하면 이미지)"""
    try:
        time.sleep(1)
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # 불필요 태그 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "button"]): 
            tag.decompose()

        # 본문 영역 탐색
        content_area = soup.select_one('.user_content, .recruit_view_cont, .view_con, .job_detail, body')
        text_content = content_area.get_text(separator="\n", strip=True) if content_area else ""
        
        # 텍스트가 너무 짧으면 이미지 수집
        if len(text_content) < 150 and content_area:
            imgs = content_area.find_all('img')
            img_urls = [urljoin(url, i.get('src') or i.get('data-src')) for i in imgs if i.get('src') or i.get('data-src')]
            clean_imgs = [i for i in img_urls if not any(x in i.lower() for x in ["icon", "logo", "common"])]
            if clean_imgs: 
                return "[이미지 공고] " + ", ".join(clean_imgs[:3])  # 최대 3개만

        return text_content[:15000] if len(text_content) > 50 else "상세 링크 참조"
    except Exception as e:
        print(f"  [상세수집 실패] {url[:50]}... - {e}")
        return "수집 실패"

def get_bep_jobs():
    """BEP(워터) 수집: 개선된 버전"""
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    
    try:
        print("  [BEP 수집 시작]")
        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 디버깅: 페이지 구조 확인
        print(f"  [BEP 응답코드] {res.status_code}")
        
        # 전략 1: recruitmentView 링크 찾기
        links = soup.find_all('a', href=re.compile(r'recruitmentView'))
        print(f"  [전략1] recruitmentView 링크 {len(links)}개 발견")
        
        # 전략 2: 테이블/리스트 구조에서 찾기
        if not links:
            # tbody 내 tr 탐색
            rows = soup.select('tbody tr')
            print(f"  [전략2] 테이블 행 {len(rows)}개 탐색")
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_text = row.get_text()
                
                # '워터', '전기차', '충전' 키워드가 있는 행만
                if any(keyword in row_text for keyword in ["워터", "전기차", "충전", "모집중"]):
                    a_tag = row.find('a', href=True)
                    if a_tag:
                        links.append(a_tag)
        
        # 전략 3: 전체 a 태그에서 필터링
        if not links:
            all_links = soup.find_all('a', href=True)
            print(f"  [전략3] 전체 링크 {len(all_links)}개 탐색")
            
            for a in all_links:
                href = a.get('href', '')
                text = a.get_text(strip=True)
                
                # Career 관련 링크이고, 의미있는 텍스트가 있는 경우
                if 'recruitment' in href.lower() or 'career' in href.lower():
                    if len(text) > 5 and text not in ["목록", "이전", "다음", "첨부파일"]:
                        links.append(a)
        
        print(f"  [최종] {len(links)}개 링크 처리 시작")
        
        # 링크 처리
        for l in links:
            href = l.get('href', '').strip()
            if not href or href in ['#', 'javascript:']:
                continue
                
            full_link = urljoin("https://bep.co.kr", href)
            title = l.get_text(" ", strip=True)
            title = re.sub(r'\s+', ' ', title)  # 연속 공백 제거
            title = title.replace("모집중", "").replace("NEW", "").strip()
            
            # 유효성 검사
            if not title or len(title) < 3:
                continue
            if title in ["목록", "이전", "다음", "HOME", "채용공고", "첨부파일"]:
                continue
            
            # 중복 방지
            if any(j[3] == full_link for j in jobs):
                continue
            
            print(f"    ✓ {title[:30]}")
            jobs.append(['BEP(워터)', title, "공고 확인", full_link])
        
        print(f"  [BEP 수집 완료] {len(jobs)}건")
        
    except Exception as e:
        print(f"  [BEP 수집 오류] {e}")
        # 실패 시에도 빈 리스트 반환 (프로그램 중단 방지)
    
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
                    
                    link = ("https://www.saramin.co.kr" + title_tag['href']).strip()
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
    
    # 1. 기존 데이터 로드 (수정된 컬럼 구조)
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

    # 3. 신규 공고 알림 및 master 업데이트
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

    # 4. 채용 종료 처리
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

    # 5. Encyclopedia 업데이트 (수정된 로직)
    print(f"\n📚 백과사전 업데이트 중...")
    
    # 5-1. 신규 링크 추가 (content는 아직 없음)
    new_for_ency = df_master[~df_master['link'].isin(df_ency['link'])].copy()
    
    if not new_for_ency.empty:
        print(f"  • 신규 엔트리 {len(new_for_ency)}건 추가")
        for _, row in new_for_ency.iterrows():
            new_row = pd.DataFrame([{
                'link': row['link'],
                'company': row['company'],
                'title': row['title'],
                'content': '',  # 일단 빈 값
                'first_seen': row['first_seen'],
                'completed_date': None,
                'last_updated': None
            }])
            df_ency = pd.concat([df_ency, new_row], ignore_index=True)
    
    # 5-2. 종료된 공고의 completed_date 업데이트
    closed_links = closed_jobs['link'].tolist() if not closed_jobs.empty else []
    if closed_links:
        print(f"  • 종료 공고 {len(closed_links)}건 날짜 기록")
        df_ency.loc[df_ency['link'].isin(closed_links), 'completed_date'] = today
    
    # 5-3. content 수집 대상 선정 (중복 수집 방지)
    retry_keywords = ["수집 실패", "로그인", "상세 링크 참조"]
    needs_content = (
        (df_ency['content'].isna()) | 
        (df_ency['content'] == '') | 
        (df_ency['content'].str.len() < 150) |
        (df_ency['content'].apply(lambda x: any(k in str(x) for k in retry_keywords)))
    )
    
    # 현재 활성 공고 중에서만 수집 (종료된 공고는 제외)
    active_and_needs = df_ency[needs_content & df_ency['link'].isin(active_links)]
    
    if not active_and_needs.empty:
        print(f"  • 상세 내용 수집 대상: {len(active_and_needs)}건")
        
        for idx, row in active_and_needs.iterrows():
            link = row['link']
            print(f"    [{idx+1}/{len(active_and_needs)}] {row['company']} - {row['title'][:30]}")
            
            content = fetch_detail_content(link)
            df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            time.sleep(0.5)  # 서버 부하 방지

    # 6. 최종 중복 제거 및 정렬
    print(f"\n💾 파일 저장 중...")
    
    for df in [df_master, df_comp, df_ency]:
        if 'link' in df.columns:
            df['link'] = df['link'].astype(str).str.strip()
            df.drop_duplicates(subset=['link'], keep='first', inplace=True)

    # Encyclopedia 정렬: 회사명 내림차순, first_seen 내림차순
    if 'company' in df_ency.columns and 'first_seen' in df_ency.columns:
        df_ency = df_ency.sort_values(by=['company', 'first_seen'], ascending=[False, False])

    # 저장
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
