import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

class JobCollector:
    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless") # 필요 시 주석 처리하여 브라우저 뜨는 것을 확인하세요
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self.options)
        self.results = []

    def wait_random(self, min_sec=2, max_sec=4):
        time.sleep(random.uniform(min_sec, max_sec))

    def crawl_saramin(self, company):
        """사람인: 가장 최근 구조 반영"""
        url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}"
        self.driver.get(url)
        self.wait_random(3, 5) # 로딩 대기 시간 증가
        
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        # 사람인의 검색 결과 영역 선택자 보강
        jobs = soup.select('.item_recruit') 
        
        found_count = 0
        for job in jobs:
            try:
                title_el = job.select_one('.job_tit a')
                corp_el = job.select_one('.corp_name a')
                
                if title_el and corp_el:
                    title = title_el.text.strip()
                    link = "https://www.saramin.co.kr" + title_el['href']
                    comp_name = corp_el.text.strip()
                    
                    # 검색어가 포함되어 있는지 확인
                    if company in comp_name:
                        self.results.append({'site': '사람인', 'company': comp_name, 'title': title, 'link': link})
                        found_count += 1
            except Exception as e:
                continue
        print(f"  - 사람인 '{company}': {found_count}건 발견")

    def crawl_jobkorea(self, company):
        """잡코리아: 통합검색 페이지 구조 반영"""
        url = f"https://www.jobkorea.co.kr/Search/?stext={company}"
        self.driver.get(url)
        self.wait_random(3, 5)
        
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        # 잡코리아는 .list-post 또는 .item 클래스를 사용함
        jobs = soup.select('.list-post .post') or soup.select('.item')
        
        found_count = 0
        for job in jobs:
            try:
                title_el = job.select_one('.title') or job.select_one('.tit')
                corp_el = job.select_one('.name') or job.select_one('.corp')
                
                if title_el and corp_el:
                    title = title_el.text.strip()
                    # 링크 추출 (a 태그가 자식으로 있는 경우 대응)
                    link_tag = title_el if title_el.name == 'a' else title_el.find('a')
                    link = "https://www.jobkorea.co.kr" + link_tag['href']
                    comp_name = corp_el.text.strip()
                    
                    if company in comp_name:
                        self.results.append({'site': '잡코리아', 'company': comp_name, 'title': title, 'link': link})
                        found_count += 1
            except Exception:
                continue
        print(f"  - 잡코리아 '{company}': {found_count}건 발견")

    def crawl_wanted(self, company):
        """원티드: data-cy 속성 활용"""
        url = f"https://www.wanted.co.kr/search?query={company}&tab=position"
        self.driver.get(url)
        self.wait_random(4, 6) # 원티드는 로딩이 느림
        
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        # 원티드 공고 카드 선택자
        jobs = soup.select('[data-cy="post-card"]')
        
        found_count = 0
        for job in jobs:
            try:
                title = job.select_one('.job-card-title').text.strip()
                link = "https://www.wanted.co.kr" + job.select_one('a')['href']
                comp_name = job.select_one('.job-card-company-name').text.strip()
                
                if company in comp_name:
                    self.results.append({'site': '원티드', 'company': comp_name, 'title': title, 'link': link})
                    found_count += 1
            except Exception:
                continue
        print(f"  - 원티드 '{company}': {found_count}건 발견")

    def run(self):
        # 검색 대상 기업 리스트
        companies = ["워터", "대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
        
        for name in companies:
            print(f"--- {name} 수집 시작 ---")
            self.crawl_saramin(name)
            self.crawl_jobkorea(name)
            self.crawl_wanted(name)
            self.wait_random(1, 2)
        
        self.driver.quit()
        
        if not self.results:
            print("❌ 수집된 데이터가 하나도 없습니다. 선택자 또는 네트워크를 확인하세요.")
            return

        df = pd.DataFrame(self.results)
        df = df.drop_duplicates(subset=['company', 'title'], keep='first')
        df.to_csv("jobs.csv", index=False, encoding='utf-8-sig')
        print(f"\n✅ 최종 수집 완료: 총 {len(df)}건 jobs.csv 저장됨.")

if __name__ == "__main__":
    collector = JobCollector()
    collector.run()