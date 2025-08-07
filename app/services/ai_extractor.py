from openai import AzureOpenAI, OpenAI
from typing import List, Dict, Optional
import json
import re
from datetime import datetime
from ..config import settings


class AIExtractor:
    def __init__(self, api_key: Optional[str] = None):
        self.client = None
        self.service_type = None
        
        # 优先使用Azure OpenAI
        if settings.USE_AZURE_OPENAI:
            try:
                self.client = AzureOpenAI(
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    azure_endpoint=settings.AZURE_OPENAI_BASE_URL,
                    api_version=settings.AZURE_OPENAI_API_VERSION
                )
                self.service_type = "azure"
                print(f"✅ Azure OpenAI client initialized successfully")
            except Exception as e:
                print(f"❌ Failed to initialize Azure OpenAI client: {e}")
                self.client = None
        
        # 如果Azure失败，尝试标准OpenAI
        if not self.client and (api_key or settings.OPENAI_API_KEY):
            try:
                self.client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)
                self.service_type = "openai"
                print("✅ Standard OpenAI client initialized successfully")
            except Exception as e:
                print(f"❌ Failed to initialize OpenAI client: {e}")
                self.client = None
        
        if not self.client:
            print("⚠️  No AI service available")
        
        self.test_parameters = [
            # Table 2 检测项
            "Appearance -- visual inspection",
            "IR",
            "HPLC", 
            "Assay -- HPLC (on anhydrous basis, %w/w)",
            "Single unspecified impurity",
            "BGB-24860",
            "RRT 0.56",
            "RRT 0.70", 
            "RRT 0.72-0.73",
            "RRT 0.76",
            "RRT 0.80",
            "RRT 1.10",
            "Total impurities",
            "Enantiomeric Impurity -- HPLC (%w/w)",
            "Dichloromethane",
            "Ethyl acetate", 
            "Isopropanol",
            "Methanol",
            "Tetrahydrofuran",
            
            # Table 2 Continued
            "Residue on Ignition (%w/w)",
            "Palladium (ppm)",
            "Polymorphic Form -- XRPD",
            "Water Content -- KF (%w/w)",
            
            # Table 3 检测项
            "RRT 0.83"
        ]
        
        self.system_prompt = f"""You are an expert at extracting analytical test results from Certificate of Analysis (COA) documents for pharmaceutical drug substances.

Extract the following information from the COA document:

REQUIRED BASIC INFORMATION:
1. Batch Number - Look for batch/lot numbers like "CR-C200727003-FPF24001"
2. Manufacture Date - Production date in format YYYY.MM.DD or similar
3. Manufacturer - Company name (usually "Changzhou SynTheAll Pharmaceutical Co., Ltd.")

REQUIRED TEST PARAMETERS (extract the actual RESULTS, not acceptance criteria):
{chr(10).join([f'- {param}' for param in self.test_parameters])}

IMPORTANT STANDARDIZATION RULES:
- For IR and HPLC identification tests: If result shows "Conforms", standardize to "Conforms to reference standard"
- For Polymorphic Form -- XRPD: If result shows "Conforms", standardize to "Conforms to reference standard"
- For appearance results: Extract exact description (e.g., "Yellow powder", "Light yellow solid")
- For percentages: Include the % symbol (e.g., "99.7%", "0.11%")
- For ppm values: Include "ppm" unit (e.g., "3 ppm", "ND")
- For "not detected" or "none detected": Use "ND"
- For missing or unclear results: Use "TBD"

Return the results in JSON format:
{{
    "batch_number": "extracted batch number",
    "manufacture_date": "YYYY-MM-DD format",
    "manufacturer": "manufacturer name",
    "test_results": {{
        "Appearance -- visual inspection": "exact visual description",
        "IR": "Conforms to reference standard (if conforms) or actual result",
        "HPLC": "Conforms to reference standard (if conforms) or actual result",
        "Assay -- HPLC (on anhydrous basis, %w/w)": "percentage with % symbol",
        "Single unspecified impurity": "actual result with units",
        "BGB-24860": "actual result or ND",
        "RRT 0.56": "actual result or ND",
        "RRT 0.70": "actual result or ND",
        "RRT 0.72-0.73": "actual result or ND",
        "RRT 0.76": "actual result or ND", 
        "RRT 0.80": "actual result or ND",
        "RRT 1.10": "actual result or ND",
        "Total impurities": "percentage with % symbol",
        "Enantiomeric Impurity -- HPLC (%w/w)": "actual result or ND",
        "Dichloromethane": "result with ppm or ND",
        "Ethyl acetate": "result with ppm or ND",
        "Isopropanol": "result with ppm or ND", 
        "Methanol": "result with ppm or ND",
        "Tetrahydrofuran": "result with ppm or ND",
        "Residue on Ignition (%w/w)": "percentage with % symbol",
        "Palladium (ppm)": "result with ppm",
        "Polymorphic Form -- XRPD": "Conforms to reference standard (if conforms) or actual result",
        "Water Content -- KF (%w/w)": "percentage with % symbol",
        "RRT 0.83": "actual result or ND"
    }}
}}

CRITICAL INSTRUCTIONS:
- Extract only the ACTUAL RESULTS from the results column, never the acceptance criteria
- For identification tests (IR, HPLC, Polymorphic Form), always use full phrase "Conforms to reference standard" when result indicates conformance
- Be precise with units and formatting
- Maintain consistency in result reporting"""
    
    async def extract_coa_batch_data(self, text: str, filename: str) -> Dict:
        """Extract COA batch data based on template parameters"""
        print(f"🤖 Starting COA batch data extraction for {filename}")
        print(f"📋 Extracting {len(self.test_parameters)} test parameters")
        
        if not self.client:
            print("❌ No AI client available")
            return self._create_empty_batch_info(filename)
        
        try:
            service_name = "Azure OpenAI" if self.service_type == "azure" else "OpenAI"
            print(f"🔍 Calling {service_name} API for batch data extraction...")
            response = await self._call_ai_service(text)
            result = self._parse_batch_ai_response(response, filename)
            print(f"✅ AI extraction completed for {filename}")
            return result
        except Exception as e:
            print(f"❌ AI extraction failed: {str(e)}")
            return self._create_empty_batch_info(filename)
    
    async def _call_ai_service(self, text: str) -> str:
        """Call AI service for extraction"""
        # Increase text limit for comprehensive COA analysis
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
            print(f"📄 Text truncated to {max_chars} characters for API call")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Extract all test results from this COA document:\n\n{text}"}
        ]
        
        try:
            if self.service_type == "azure":
                response = self.client.chat.completions.create(
                    model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                    messages=messages,
                    temperature=0.05,  # Lower temperature for more precise extraction
                    max_tokens=2000    # Increase tokens for comprehensive results
                )
            else:
                response = self.client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.05,
                    max_tokens=2000
                )
            
            return response.choices[0].message.content
            
        except Exception as e:
            service_name = "Azure OpenAI" if self.service_type == "azure" else "OpenAI"
            print(f"❌ {service_name} API call failed: {str(e)}")
            raise e
    
    def _parse_batch_ai_response(self, response: str, filename: str) -> Dict:
        """Parse AI response into batch data structure"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response)
            
            # Create batch information structure
            batch_info = {
                "filename": filename,
                "batch_number": data.get("batch_number", ""),
                "manufacture_date": data.get("manufacture_date", ""),
                "manufacturer": data.get("manufacturer", ""),
                "test_results": {}
            }
            
            # Extract test results for all parameters
            test_results_data = data.get("test_results", {})
            
            for param in self.test_parameters:
                if param in test_results_data:
                    batch_info["test_results"][param] = test_results_data[param]
                else:
                    # Default value if not found
                    batch_info["test_results"][param] = "TBD"
            
            # Display extraction results
            print(f"\n📊 Extraction Results for {filename}:")
            print("=" * 70)
            print(f"📦 Batch Number: {batch_info['batch_number']}")
            print(f"📅 Manufacture Date: {batch_info['manufacture_date']}")
            print(f"🏭 Manufacturer: {batch_info['manufacturer'][:50]}..." if len(batch_info['manufacturer']) > 50 else f"🏭 Manufacturer: {batch_info['manufacturer']}")
            print(f"🧪 Test Results Extracted: {len([v for v in batch_info['test_results'].values() if v not in ['TBD', 'ND', '']])}/{len(self.test_parameters)}")
            
            # Display key test results
            key_results = [
                "Appearance -- visual inspection",
                "Assay -- HPLC (on anhydrous basis, %w/w)",
                "Total impurities", 
                "Water Content -- KF (%w/w)",
                "Residue on Ignition (%w/w)"
            ]
            
            print("\n🔬 Key Test Results:")
            for key in key_results:
                value = batch_info["test_results"].get(key, "TBD")
                if value not in ["TBD", "ND", ""]:
                    print(f"   ✓ {key}: {value}")
                else:
                    print(f"   ⚪ {key}: {value}")
            
            print("=" * 70)
            return batch_info
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON from AI response: {str(e)}")
            print(f"📝 Raw response preview: {response[:300]}...")
            return self._create_empty_batch_info(filename)
        except Exception as e:
            print(f"❌ Failed to parse AI response: {str(e)}")
            return self._create_empty_batch_info(filename)
    
    def _create_empty_batch_info(self, filename: str) -> Dict:
        """Create empty batch info structure with all test parameters"""
        batch_info = {
            "filename": filename,
            "batch_number": "",
            "manufacture_date": "",
            "manufacturer": "",
            "test_results": {}
        }
        
        # Initialize all test parameters with empty values
        for param in self.test_parameters:
            batch_info["test_results"][param] = "TBD"
        
        return batch_info
    
    def get_test_parameters(self) -> List[str]:
        """Get the list of all test parameters being extracted"""
        return self.test_parameters.copy()
    
    def validate_batch_data(self, batch_data: Dict) -> Dict:
        """Validate and clean batch data"""
        # Clean batch number
        if batch_data.get("batch_number"):
            batch_data["batch_number"] = batch_data["batch_number"].strip()
        
        # Standardize date format
        if batch_data.get("manufacture_date"):
            date_str = batch_data["manufacture_date"].replace(".", "-")
            batch_data["manufacture_date"] = date_str
        
        # Clean manufacturer name
        if batch_data.get("manufacturer"):
            batch_data["manufacturer"] = batch_data["manufacturer"].strip()
        
        # Clean test results
        test_results = batch_data.get("test_results", {})
        for param, value in test_results.items():
            if isinstance(value, str):
                # Clean whitespace
                cleaned_value = value.strip()
                # Standardize common values
                if cleaned_value.lower() in ["not detected", "none detected", "nd"]:
                    cleaned_value = "ND"
                elif cleaned_value.lower() in ["to be determined", "tbd", ""]:
                    cleaned_value = "TBD"
                elif cleaned_value.lower() in ["conforms", "conform"]:
                    # Standardize "Conforms" to full phrase for identification tests
                    if param in ["IR", "HPLC", "Polymorphic Form -- XRPD"]:
                        cleaned_value = "Conforms to reference standard"
                    else:
                        cleaned_value = "Conforms"
                elif "conforms to reference" in cleaned_value.lower():
                    cleaned_value = "Conforms to reference standard"
                # Additional standardization for specific test types
                if param == "Appearance -- visual inspection":
                    # Capitalize first letter for appearance descriptions
                    if cleaned_value and cleaned_value != "TBD" and cleaned_value != "ND":
                        cleaned_value = cleaned_value[0].upper() + cleaned_value[1:] if len(cleaned_value) > 1 else cleaned_value.upper()
                
                test_results[param] = cleaned_value
        
        return batch_data