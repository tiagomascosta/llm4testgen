#!/usr/bin/env python3
"""
Enhanced Dataset Builder - Consolidated Version
Robust method detection with multiple strategies for bulletproof method identification from git diffs.
"""

import os
import re
import sys
import tempfile
import subprocess
import shutil
import csv
import logging
import javalang
from pathlib import Path
from datasets import load_dataset
from typing import List, Optional, Dict
from dataclasses import dataclass

# Add the main implementation to the path
sys.path.append('/home/tiago/Desktop/Faculdade/Thesis/implementation')

# Import existing functionality with proper path handling
sys.path.append('/home/tiago/Desktop/Faculdade/Thesis/implementation/experiments/dataset/src/utils')
from halstead_volume import compute_halstead_volume
from cyclomatic_complexity import compute_cyclomatic_complexity
from maintainability_index import compute_maintainability_index, mi_category

# Also import the source analysis functionality
sys.path.append('/home/tiago/Desktop/Faculdade/Thesis/implementation')
# Import slice_method directly to avoid import issues
try:
    from source_analysis.slice_extractor import SliceExtractor
    from source_analysis.method_slicer import slice_method
except ImportError:
    # Fallback: define a simple slice_method function
    def slice_method(repo_root, method_spec):
        """Fallback slice_method implementation."""
        return None

@dataclass
class MethodChange:
    """Represents a method that was changed."""
    method_name: str
    class_name: str
    full_signature: str
    start_line: int
    end_line: int
    confidence_score: float
    change_type: str  # 'modified', 'added', 'deleted'
    affected_lines: List[int]

class RobustMethodDetector:
    """Bulletproof method change detection using multiple strategies."""
    
    def __init__(self, logger=None):
        print = logger or logging.getLogger(__name__)
    
    def detect_changed_methods(self, patch: str, src_lines: List[str], file_path: str) -> List[MethodChange]:
        """
        Detect all methods that were changed using multiple strategies.
        
        Args:
            patch: Git patch content
            src_lines: Source file lines (buggy version)
            file_path: Path to the source file
            
        Returns:
            List of MethodChange objects with confidence scores
        """
        strategies = [
            self._strategy_patch_line_analysis,
            self._strategy_ast_method_boundaries,
            self._strategy_signature_matching,
            self._strategy_context_analysis
        ]
        
        all_detections = []
        
        for strategy in strategies:
            try:
                detections = strategy(patch, src_lines, file_path)
                if detections:
                    print(f"Strategy {strategy.__name__} found {len(detections)} methods")
                    all_detections.extend(detections)
                else:
                    print(f"Strategy {strategy.__name__} found 0 methods")
            except Exception as e:
                print(f"Strategy {strategy.__name__} failed: {e}")
        
        # Merge and deduplicate detections
        merged_detections = self._merge_detections(all_detections)
        
        # Sort by confidence score
        merged_detections.sort(key=lambda x: x.confidence_score, reverse=True)
        
        return merged_detections
    
    def _strategy_patch_line_analysis(self, patch: str, src_lines: List[str], file_path: str) -> List[MethodChange]:
        """Strategy 1: Use the original SliceExtractor approach for robust method detection."""
        detections = []
        
        try:
            # Parse patch to get all changed line numbers (same as original)
            changed_lines = self._extract_changed_lines_from_patch(patch)
            
            if not changed_lines:
                return detections
            
            # Use SliceExtractor like the original script
            from source_analysis.slice_extractor import SliceExtractor
            import javalang
            
            # Parse the source file
            tree = javalang.parse.parse('\n'.join(src_lines))
            
            # Use SliceExtractor to find all methods and their boundaries
            all_methods = []
            slicer = SliceExtractor()
            
            for path, node in tree.filter(javalang.tree.MethodDeclaration):
                if not node.position:
                    continue
                    
                method_name = node.name
                method_start = node.position.line
                
                # Use SliceExtractor's _extract_method_impl to get the method boundaries
                try:
                    method_text = slicer._extract_method_impl("\n".join(src_lines), node, include_javadoc=False)
                    if method_text:
                        # Calculate method end line based on the extracted text
                        method_lines = method_text.splitlines()
                        method_end = method_start + len(method_lines) - 1
                        all_methods.append((method_name, method_start, method_end, node))
                except Exception as e:
                    # Could not extract method
                    continue
            
            # Find which method contains the target lines
            methods_with_target_lines = {}
            for target in changed_lines:
                target_found = False
                
                # Only use exact line match - no heuristic
                for method_name, start, end, node in all_methods:
                    if start <= target <= end:
                        if method_name not in methods_with_target_lines:
                            methods_with_target_lines[method_name] = []
                        methods_with_target_lines[method_name].append(target)
                        target_found = True
                        break
                
                if not target_found:
                    print(f"Target line {target} is not in any method")
            
            # Create detections for methods that contain target lines
            # Use the original's better selection logic: most target lines, then earliest line
            if methods_with_target_lines:
                best_method = max(methods_with_target_lines.items(), 
                                 key=lambda x: (len(x[1]), x[1][0]))  # Most target lines, then earliest line
                
                method_name = best_method[0]
                affected_lines = best_method[1]
                
                # Find the method details
                for method_name_check, start, end, node in all_methods:
                    if method_name_check == method_name:
                        class_name = self._get_class_name_from_path(path)
                        confidence = len(affected_lines) / len(changed_lines)
                        
                        detections.append(MethodChange(
                            method_name=method_name,
                            class_name=class_name,
                            full_signature=self._build_method_signature(node),
                            start_line=start,
                            end_line=end,
                            confidence_score=confidence,
                            change_type='modified',
                            affected_lines=affected_lines
                        ))
                        break
        
        except Exception as e:
            print(f"Strategy _strategy_patch_line_analysis failed: {e}")
        
        return detections
    
    def _strategy_ast_method_boundaries(self, patch: str, src_lines: List[str], file_path: str) -> List[MethodChange]:
        """Strategy 2: Use AST to find exact method boundaries and match with patch."""
        detections = []
        
        try:
            # Parse the source file with AST
            tree = javalang.parse.parse('\n'.join(src_lines))
            
            # Find all method declarations
            for path, node in tree.filter(javalang.tree.MethodDeclaration):
                if not node.position:
                    continue
                
                method_name = node.name
                start_line = node.position.line
                
                # Find method end by looking for closing brace
                end_line = self._find_method_end_line(src_lines, start_line)
                
                # Check if this method was affected by the patch
                changed_lines = self._extract_changed_lines_from_patch(patch)
                affected_lines = [line for line in changed_lines if start_line <= line <= end_line]
                
                if affected_lines:
                    # Calculate confidence based on coverage
                    confidence = len(affected_lines) / max(1, end_line - start_line + 1)
                    
                    # Get class name
                    class_name = self._get_class_name_from_path(path)
                    
                    detections.append(MethodChange(
                        method_name=method_name,
                        class_name=class_name,
                        full_signature=self._build_method_signature(node),
                        start_line=start_line,
                        end_line=end_line,
                        confidence_score=confidence,
                        change_type='modified',
                        affected_lines=affected_lines
                    ))
        
        except Exception as e:
            print(f"AST parsing failed: {e}")
        
        return detections
    
    def _strategy_signature_matching(self, patch: str, src_lines: List[str], file_path: str) -> List[MethodChange]:
        """Strategy 3: Look for method signatures in the patch additions/removals."""
        detections = []
        
        # Extract added and removed lines from patch
        added_lines = []
        removed_lines = []
        
        for line in patch.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                added_lines.append(line[1:])
            elif line.startswith('-') and not line.startswith('---'):
                removed_lines.append(line[1:])
        
        # Look for method signatures in the changes
        method_signatures = []
        for line in added_lines + removed_lines:
            # Look for method declarations
            method_match = re.search(r'(public|private|protected)?\s*(static)?\s*(\w+)\s+(\w+)\s*\(', line)
            if method_match:
                method_signatures.append(method_match.group(4))
        
        # Find methods by name in the source file
        for method_name in set(method_signatures):
            try:
                tree = javalang.parse.parse('\n'.join(src_lines))
                
                for path, node in tree.filter(javalang.tree.MethodDeclaration):
                    if node.name == method_name and node.position:
                        start_line = node.position.line
                        end_line = self._find_method_end_line(src_lines, start_line)
                        class_name = self._get_class_name_from_path(path)
                        
                        detections.append(MethodChange(
                            method_name=method_name,
                            class_name=class_name,
                            full_signature=self._build_method_signature(node),
                            start_line=start_line,
                            end_line=end_line,
                            confidence_score=0.8,  # High confidence for signature match
                            change_type='modified',
                            affected_lines=[]
                        ))
                        break
            except Exception as e:
                print(f"Error finding method {method_name}: {e}")
        
        return detections
    
    def _strategy_context_analysis(self, patch: str, src_lines: List[str], file_path: str) -> List[MethodChange]:
        """Strategy 4: Analyze context around changed lines to find methods."""
        detections = []
        
        try:
            changed_lines = self._extract_changed_lines_from_patch(patch)
            
            # Find all methods in the file
            tree = javalang.parse.parse('\n'.join(src_lines))
            
            for path, node in tree.filter(javalang.tree.MethodDeclaration):
                if not node.position:
                    continue
                
                method_name = node.name
                start_line = node.position.line
                end_line = self._find_method_end_line(src_lines, start_line)
                
                # Check if any changed line is near this method (within 5 lines)
                for changed_line in changed_lines:
                    if abs(changed_line - start_line) <= 5 or abs(changed_line - end_line) <= 5:
                        class_name = self._get_class_name_from_path(path)
                        confidence = 0.3  # Lower confidence for context-based detection
                        
                        detections.append(MethodChange(
                            method_name=method_name,
                            class_name=class_name,
                            full_signature=self._build_method_signature(node),
                            start_line=start_line,
                            end_line=end_line,
                            confidence_score=confidence,
                            change_type='modified',
                            affected_lines=[changed_line]
                        ))
                        break
        
        except Exception as e:
            print(f"Error finding methods: {e}")
        
        return detections
    
    def _merge_detections(self, detections: List[MethodChange]) -> List[MethodChange]:
        """Merge duplicate detections and combine confidence scores."""
        merged = {}
        
        for detection in detections:
            key = (detection.method_name, detection.class_name)
            if key in merged:
                # Combine confidence scores and affected lines
                merged[key].confidence_score = max(merged[key].confidence_score, detection.confidence_score)
                merged[key].affected_lines = list(set(merged[key].affected_lines + detection.affected_lines))
            else:
                merged[key] = detection
        
        return list(merged.values())
    
    def _extract_changed_lines_from_patch(self, patch: str) -> List[int]:
        """Extract all line numbers that were changed in the patch."""
        changed_lines = []
        
        for line in patch.splitlines():
            if line.startswith('@@'):
                match = re.search(r'@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@', line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) else 1
                    
                    # Add all lines in this hunk
                    for i in range(old_count):
                        changed_lines.append(old_start + i)
        
        return changed_lines
    
    def _find_method_end_line(self, src_lines: List[str], start_line: int) -> int:
        """Find the end line of a method starting at start_line."""
        brace_count = 0
        in_method = False
        
        for i, line in enumerate(src_lines[start_line-1:], start_line):
            for char in line:
                if char == '{':
                    brace_count += 1
                    in_method = True
                elif char == '}':
                    brace_count -= 1
                    if in_method and brace_count == 0:
                        return i
        
        # Fallback: return start_line if we can't find the end
        return start_line
    
    def _get_class_name_from_path(self, path) -> str:
        """Extract class name from AST path."""
        # Find the main (outer) class name, not nested classes
        # The SliceExtractor will automatically search nested classes
        for node in reversed(path):
            if isinstance(node, javalang.tree.ClassDeclaration):
                return node.name
        return "Unknown"
    
    def _build_method_signature(self, method_node) -> str:
        """Build method signature from AST node."""
        parts = []
        
        if method_node.modifiers:
            parts.extend(method_node.modifiers)
        
        if method_node.return_type:
            parts.append(str(method_node.return_type))
        
        parts.append(method_node.name)
        
        params = []
        for param in method_node.parameters:
            param_str = str(param.type) + " " + param.name
            params.append(param_str)
        
        signature = " ".join(parts) + "(" + ", ".join(params) + ")"
        return signature

def calculate_loc(snippet: str) -> int:
    """Calculate Lines of Code excluding comments and blank lines."""
    loc = 0
    in_multiline_comment = False
    
    for line in snippet.splitlines():
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
            
        # Handle single-line comments
        if line.startswith('//'):
            continue
            
        # Handle multi-line comments
        if '/*' in line:
            in_multiline_comment = True
        if '*/' in line:
            in_multiline_comment = False
            continue
            
        # Skip lines in multi-line comments
        if in_multiline_comment:
            continue
            
        # Count non-comment, non-empty lines
        loc += 1
    
    return loc

def process_record_enhanced(rec, logger):
    """
    Enhanced processing with robust method detection.
    Uses multiple strategies to identify changed methods.
    """
    bug_id = rec["bid"]
    pid = rec["pid"]
    clone_url = rec["clone_url"]
    bug_hash = rec["previous_commit_hash"]
    fix_hash = rec["commit_hash"]
    patch = rec["bug_patch"]
    
    # Filter out non-code patches
    non_code_patch = rec.get("non_code_patch", "")
    change_type = rec.get("change_type", "")
    
    if non_code_patch and non_code_patch.strip():
        # Skipping non-code changes
        raise ValueError("Non-code patch detected")
    
    if change_type != "SOURCE_ONLY":
        # Skipping non-source changes
        raise ValueError(f"Change type {change_type} is not SOURCE_ONLY")
    
    print(f"Processing record {bug_id} (project: {pid})")
    
    # Create temporary directory for cloning
    with tempfile.TemporaryDirectory() as tmp:
        print(f"Cloning repository to {tmp}")
        
        # Clone the repository
        subprocess.run(
            ["git", "clone", clone_url, tmp],
            check=True, stdout=subprocess.DEVNULL
        )

        # Check out buggy commit
        print(f"Checking out buggy commit: {bug_hash}")
        subprocess.run(
            ["git", "checkout", bug_hash],
            cwd=tmp, check=True, stdout=subprocess.DEVNULL
        )
        
        # Extract file path from patch
        file_rel = next(
            l for l in patch.splitlines() if l.startswith("diff --git")
        ).split()[2][2:]  # Remove 'b/' prefix
        
        full_path = os.path.join(tmp, file_rel)
        
        if not os.path.exists(full_path):
            print(f"File not found: {full_path}")
            raise FileNotFoundError(f"File not found: {full_path}")
        
        # Load the buggy version of the file
        with open(full_path, encoding="utf-8") as f:
            src_lines_bug = f.read().splitlines()

        print(f"Buggy file loaded: {len(src_lines_bug)} total lines")
        
        # Use enhanced robust method detection
        print("Using enhanced robust method detection...")
        detector = RobustMethodDetector(logger)
        method_changes = detector.detect_changed_methods(patch, src_lines_bug, full_path)
        
        if not method_changes:
            raise RuntimeError("No methods detected as changed")
        
        # Log all detected methods
        print(f"Detected {len(method_changes)} changed methods:")
        for i, change in enumerate(method_changes):
            print(f"  {i+1}. {change.method_name} (confidence: {change.confidence_score:.2f})")
        
        # Select the best method (highest confidence)
        best_method = method_changes[0]
        print(f"Selected method: {best_method.method_name} (confidence: {best_method.confidence_score:.2f})")
        
        # Extract the method using slice_method for final extraction
        file_rel_clean = file_rel
        if file_rel_clean.startswith('src/main/java/'):
            file_rel_clean = file_rel_clean[14:]  # Remove 'src/main/java/' (14 characters)
        class_name = file_rel_clean.replace('.java', '').replace('/', '.')
        method_spec = f"{class_name}#{best_method.method_name}"
        
        print(f"Extracting method using slice_method: {method_spec}")
        snippet = slice_method(Path(tmp), method_spec)
        
        if not snippet:
            raise RuntimeError(f"slice_method failed to extract method {method_spec}")
        
        # Calculate LOC (excluding comments and blank lines)
        loc = calculate_loc(snippet)
        
        # Compute metrics
        hal_vol = compute_halstead_volume(snippet)
        cc_val = compute_cyclomatic_complexity(snippet)
        mi_val = compute_maintainability_index(loc, hal_vol, cc_val)
        mi_cat = mi_category(mi_val)
        
        print(f"Method Metrics - LOC: {loc}, Halstead: {hal_vol:.2f}, CC: {cc_val}, MI: {mi_val:.2f} ({mi_cat})")
        
        # Log detailed extraction info
        print(f"\n{'='*60}")
        print(f"ENHANCED EXTRACTION - Bug ID: {bug_id}")
        print(f"Method: {best_method.method_name}")
        print(f"Class: {best_method.class_name}")
        print(f"Confidence: {best_method.confidence_score:.2f}")
        print(f"LOC: {loc}")
        print(f"{'='*60}")
        
        # Return the record data
        return {
            "project": pid,
            "repo_url": clone_url,
            "bug_commit_hash": bug_hash,
            "bug_file_path": file_rel,
            "fix_commit_hash": fix_hash,
            "method_name": best_method.method_name,
            "method_signature": best_method.full_signature,
            "loc": loc,
            "cyclomatic_complexity": cc_val,
            "halstead_volume": hal_vol,
            "maintainability_index": mi_val
        }


def manual_method_extraction(source_content: str, method_name: str) -> Optional[str]:
    """Manual method extraction as fallback when slice_method fails."""
    try:
        # Simple regex-based method extraction
        # Look for method definition
        method_pattern = rf'(public|private|protected)?\s*(static)?\s*\w+\s+{re.escape(method_name)}\s*\([^)]*\)\s*\{{'
        match = re.search(method_pattern, source_content)
        
        if not match:
            return None
        
        # Find the start of the method
        start_pos = match.start()
        
        # Find the matching closing brace
        brace_count = 0
        in_method = False
        method_start = None
        
        for i, char in enumerate(source_content[start_pos:], start_pos):
            if char == '{':
                if not in_method:
                    in_method = True
                    method_start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if in_method and brace_count == 0:
                    # Found the end of the method
                    return source_content[method_start:i+1]
        
        return None
        
    except Exception as e:
        print(f"Manual method extraction failed: {e}")
        return None

def main_enhanced(max_records=None):
    """Main function with enhanced robust method detection."""
    # Set up paths
    root = Path("/home/tiago/Desktop/Faculdade/Thesis/implementation/experiments/dataset")
    dataset_csv = root / "dataset_v2.csv"
    
    # Set up minimal logging
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger(__name__)
    
    print("Starting ENHANCED dataset builder")
    print(f"Output CSV: {dataset_csv}")
    if max_records:
        print(f"TESTING MODE: Processing only {max_records} records")
    
    # Load dataset
    print("Loading GitBug-Java dataset...")
    dataset = load_dataset("gitbugactions/gitbug-java", split="train")
    print(f"Loaded {len(dataset)} records")
    
    # Limit dataset if max_records is specified
    if max_records:
        dataset = dataset.select(range(min(max_records, len(dataset))))
        print(f"Limited to {len(dataset)} records for testing")
    else:
        print(f"Processing all {len(dataset)} records")
    
    # Process records
    successful_records = []
    failed_records = []
    
    for i, rec in enumerate(dataset):
        try:
            print(f"\n{'='*80}")
            print(f"Processing record {i+1}/{len(dataset)}")
            print(f"{'='*80}")
            
            result = process_record_enhanced(rec, logger)
            successful_records.append(result)
            
            print(f"✅ Successfully processed record {i+1}")
            
        except Exception as e:
            print(f"❌ Failed to process record {i+1}: {str(e)}")
            failed_records.append({
                "record_index": i,
                "bug_id": rec.get("bid", "unknown"),
                "error": str(e)
            })
    
    # Save results
    print(f"\n{'='*80}")
    print("SAVING ENHANCED RESULTS")
    print(f"{'='*80}")
    
    if successful_records:
        print(f"Saving {len(successful_records)} successful records to {dataset_csv}")
        
        # Define the exact column order we want
        fieldnames = [
            "project",
            "repo_url", 
            "bug_commit_hash",
            "bug_file_path",
            "fix_commit_hash",
            "method_name",
            "method_signature",
            "loc",
            "cyclomatic_complexity",
            "halstead_volume",
            "maintainability_index"
        ]
        
        with open(dataset_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for record in successful_records:
                writer.writerow(record)
        
        print(f"✅ Enhanced dataset saved successfully")
    else:
        print("No successful records to save")
    
    # Summary
    print(f"\n{'='*80}")
    print("ENHANCED FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Total records processed: {len(dataset)}")
    print(f"Successful extractions: {len(successful_records)} ({len(successful_records)/len(dataset)*100:.1f}%)")
    print(f"Failed extractions: {len(failed_records)} ({len(failed_records)/len(dataset)*100:.1f}%)")
    
    if failed_records:
        print("\nFailed records:")
        for fail in failed_records[:10]:
            print(f"  Record {fail['record_index']}: {fail['bug_id']} - {fail['error']}")
        if len(failed_records) > 10:
            print(f"  ... and {len(failed_records) - 10} more failures")
    
    print("Enhanced dataset builder completed!")

if __name__ == "__main__":
    # For full dataset processing
    main_enhanced()
    
    # For testing, uncomment the line below to process only 3 records
    #main_enhanced(max_records=3)
