import requests
from bs4 import BeautifulSoup
import os
import re
import json
from tqdm import tqdm
import time
import urllib.parse

class AWSAPIDocScraper:
    def __init__(self, services=None, base_domain="https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/"):
        self.base_domain = base_domain
        self.output_dir = "aws_api_docs_consolidated"
        
        # 기본 서비스 목록
        self.default_services = [
            "ec2", "s3", "efs", "rds", "elbv2", "eks", "ecs"
        ]
        
        # 사용할 서비스 목록
        self.services = services if services else self.default_services
        
        # 출력 디렉토리 생성
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def fetch_page(self, url):
        """웹 페이지 내용을 가져옵니다."""
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Error fetching {url}: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception while fetching {url}: {e}")
            return None
    
    def get_service_url(self, service):
        """서비스 문서 URL을 생성합니다."""
        return f"{self.base_domain}{service}.html"
    
    def extract_method_links(self, html_content, service):
        """API 메서드 링크를 추출합니다."""
        soup = BeautifulSoup(html_content, 'html.parser')
        method_links = []
        
        # 서비스별 클라이언트 메서드 링크 패턴
        client_pattern = f"{service}/client/"
        
        # 모든 내부 링크 검색
        for a_tag in soup.find_all('a', {'class': 'reference internal'}):
            href = a_tag.get('href')
            method_name = a_tag.text.strip()
            
            # 클라이언트 메서드 링크만 필터링
            if href and client_pattern in href:
                # 상대 URL을 절대 URL로 변환
                method_url = urllib.parse.urljoin(self.base_domain, href)
                method_links.append((method_name, method_url))
        
        return method_links
    
    def extract_method_description(self, html_content, method_name):
        """메서드 설명만 추출합니다."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 메서드 설명 추출
        description = ""
        # 메서드 설명은 일반적으로 dl.py.method 내의 첫 번째 p 태그에 있음
        method_dl = soup.find('dl', {'class': 'py method'})
        if method_dl:
            dd_tags = method_dl.find_all('dd')
            if dd_tags and len(dd_tags) > 0:
                p_tags = dd_tags[0].find_all('p', limit=2)  # 처음 두 개의 p 태그만 가져옴
                if p_tags:
                    description = ' '.join([p.text.strip() for p in p_tags])
        
        # 설명이 없으면 다른 방법으로 시도
        if not description:
            # 페이지 제목 다음의 첫 번째 p 태그 시도
            h1_tag = soup.find('h1')
            if h1_tag:
                next_p = h1_tag.find_next('p')
                if next_p:
                    description = next_p.text.strip()
        
        return {
            'name': method_name,
            'description': description
        }
    
    def save_consolidated_markdown(self, service, method_infos):
        """서비스별로 모든 메서드 정보를 하나의 마크다운 파일로 저장합니다."""
        if not method_infos:
            return False
        
        file_path = os.path.join(self.output_dir, f"{service}.md")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            # 서비스 제목
            f.write(f"# {service.upper()} API Reference\n\n")
            
            # 메서드 수 정보
            f.write(f"Contains {len(method_infos)} API methods\n\n")
            
            # 목차
            f.write("## Table of Contents\n\n")
            for method_info in method_infos:
                method_name = method_info['name']
                f.write(f"- [{method_name}](#{method_name.lower().replace('_', '-')})\n")
            f.write("\n")
            
            # 각 메서드 정보
            for method_info in method_infos:
                method_name = method_info['name']
                description = method_info.get('description', 'No description available')
                
                f.write(f"## {method_name}\n\n")
                f.write(f"{description}\n\n")
                f.write("---\n\n")
        
        print(f"Saved consolidated markdown for {service} with {len(method_infos)} methods to {file_path}")
        return True
    
    def scrape_service(self, service, limit=None):
        """특정 서비스의 API 문서를 스크랩합니다."""
        print(f"\n--- Scraping {service.upper()} API ---")
        
        # 서비스 메인 페이지 URL
        service_url = self.get_service_url(service)
        
        # 메인 페이지 가져오기
        html_content = self.fetch_page(service_url)
        if not html_content:
            print(f"Failed to fetch {service} documentation")
            return []
        
        # 메서드 링크 추출
        method_links = self.extract_method_links(html_content, service)
        print(f"Found {len(method_links)} methods for {service}")
        
        # 처리할 메서드 수 제한 (테스트용)
        if limit:
            method_links = method_links[:limit]
        
        method_infos = []
        
        # 각 메서드 처리
        for i, (method_name, method_url) in enumerate(tqdm(method_links)):
            # 메서드 페이지 가져오기
            method_html = self.fetch_page(method_url)
            if not method_html:
                continue
            
            # 메서드 설명 추출
            method_info = self.extract_method_description(method_html, method_name)
            
            if method_info and method_info.get('description'):
                # 서비스 정보 추가
                method_info['service'] = service
                method_infos.append(method_info)
            
            # 서버 부하를 줄이기 위한 딜레이
            time.sleep(0.2)
        
        # 서비스별로 통합된 마크다운 파일 저장
        if method_infos:
            self.save_consolidated_markdown(service, method_infos)
        
        print(f"Completed scraping {service}: processed {len(method_infos)} out of {len(method_links)} methods")
        return method_infos
    
    def scrape_all_services(self, limit_per_service=None):
        """모든 서비스의 API 문서를 스크랩합니다."""
        all_method_infos = []
        
        for service in self.services:
            method_infos = self.scrape_service(service, limit=limit_per_service)
            all_method_infos.extend(method_infos)
        
        print(f"\nTotal methods scraped across all services: {len(all_method_infos)}")
        return all_method_infos

if __name__ == "__main__":
    # AWS API 문서 스크래퍼 초기화 및 실행
    scraper = AWSAPIDocScraper()
    method_infos = scraper.scrape_all_services()
