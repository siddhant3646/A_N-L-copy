"""
Smart Element Handler - Enhanced DOM element interaction.

This module provides:
1. Automatic input type detection
2. Option extraction from select/radio/checkbox elements
3. Smart filling with fallback strategies
4. Integration with InputAwareResolver
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
from playwright.async_api import Page, ElementHandle

from src.patterns.input_aware_resolver import (
    InputAwareResolver, InputType, Option
)


@dataclass
class ElementInfo:
    element_type: InputType
    tag: str
    name: str
    id: str
    label: str
    placeholder: str
    options: List[Option]
    is_required: bool
    validation_pattern: Optional[str]
    element_handle: ElementHandle = None


class SmartElementHandler:
    """
    Handles form elements with intelligent answer resolution.
    """
    
    def __init__(self, resolver: InputAwareResolver = None):
        self.resolver = resolver or InputAwareResolver()
    
    async def detect_element_type(self, element: ElementHandle) -> InputType:
        try:
            tag = await element.evaluate('el => el.tagName.toLowerCase()')
            
            if tag == 'select':
                return InputType.SELECT
            
            if tag == 'textarea':
                return InputType.TEXTAREA
            
            if tag == 'input':
                input_type = await element.evaluate('el => el.type.toLowerCase()')
                
                type_map = {
                    'text': InputType.TEXT,
                    'number': InputType.NUMBER,
                    'email': InputType.EMAIL,
                    'tel': InputType.TEL,
                    'date': InputType.DATE,
                    'radio': InputType.RADIO,
                    'checkbox': InputType.CHECKBOX,
                }
                
                return type_map.get(input_type, InputType.TEXT)
            
            return InputType.TEXT
            
        except Exception as e:
            print(f"⚠️ Error detecting element type: {e}")
            return InputType.TEXT
    
    async def extract_options(self, element: ElementHandle, page: Page) -> List[Option]:
        element_type = await self.detect_element_type(element)
        options = []
        
        try:
            if element_type == InputType.SELECT:
                options = await self._extract_select_options(element)
            elif element_type == InputType.RADIO:
                options = await self._extract_radio_options(element, page)
            elif element_type == InputType.CHECKBOX:
                options = await self._extract_checkbox_options(element, page)
        except Exception as e:
            print(f"⚠️ Error extracting options: {e}")
        
        return options
    
    async def _extract_select_options(self, element: ElementHandle) -> List[Option]:
        options_data = await element.evaluate('''
            el => {
                const options = Array.from(el.options);
                return options.map((opt, i) => ({
                    value: opt.value,
                    label: opt.text.trim(),
                    index: i,
                    is_selected: opt.selected
                })).filter(o => o.value && o.label && o.value.toLowerCase() !== 'select');
            }
        ''')
        
        return [Option(**opt) for opt in options_data]
    
    async def _extract_radio_options(self, element: ElementHandle, page: Page) -> List[Option]:
        name = await element.evaluate('el => el.name')
        if not name:
            return [Option(value='true', label='Selected')]
        
        options_data = await page.evaluate('''
            radioName => {
                const radios = document.querySelectorAll(`input[type="radio"][name="${radioName}"]`);
                return Array.from(radios).map((radio, i) => {
                    let label = '';
                    const parent = radio.closest('label');
                    if (parent) {
                        label = parent.textContent.trim();
                    } else {
                        const labelEl = document.querySelector(`label[for="${radio.id}"]`);
                        if (labelEl) label = labelEl.textContent.trim();
                    }
                    return {
                        value: radio.value,
                        label: label || radio.value,
                        index: i,
                        is_selected: radio.checked
                    };
                });
            }
        ''', name)
        
        return [Option(**opt) for opt in options_data]
    
    async def _extract_checkbox_options(self, element: ElementHandle, page: Page) -> List[Option]:
        name = await element.evaluate('el => el.name')
        
        if name:
            options_data = await page.evaluate('''
                checkboxName => {
                    const checkboxes = document.querySelectorAll(`input[type="checkbox"][name="${checkboxName}"]`);
                    return Array.from(checkboxes).map((cb, i) => {
                        let label = '';
                        const parent = cb.closest('label');
                        if (parent) {
                            label = parent.textContent.trim();
                        } else {
                            const labelEl = document.querySelector(`label[for="${cb.id}"]`);
                            if (labelEl) label = labelEl.textContent.trim();
                        }
                        return {
                            value: cb.value || 'checked',
                            label: label || cb.value || 'Option',
                            index: i,
                            is_selected: cb.checked
                        };
                    });
                }
            ''', name)
            return [Option(**opt) for opt in options_data]
        else:
            label = await self._find_label(element, page)
            return [Option(
                value='checked',
                label=label or 'Checked',
                is_selected=await element.evaluate('el => el.checked')
            )]
    
    async def _find_label(self, element: ElementHandle, page: Page) -> str:
        try:
            element_id = await element.evaluate('el => el.id')
            if element_id:
                label = await page.evaluate(f'''
                    () => {{
                        const label = document.querySelector('label[for="{element_id}"]');
                        return label ? label.textContent.trim() : '';
                    }}
                ''')
                if label:
                    return label
            
            parent_label = await element.evaluate('''
                el => {
                    const parent = el.closest('label');
                    return parent ? parent.textContent.trim() : '';
                }
            ''')
            return parent_label
            
        except Exception:
            return ""
    
    async def smart_fill(
        self,
        element: ElementHandle,
        page: Page,
        answer: str,
        question: str = "",
        platform: str = "default"
    ) -> Tuple[bool, str]:
        element_type = await self.detect_element_type(element)
        options = await self.extract_options(element, page)
        
        result = self.resolver.resolve(
            answer=answer,
            input_type=element_type,
            options=options,
            question=question
        )
        
        try:
            if element_type == InputType.SELECT:
                success = await self._fill_select(element, result.matched_option)
            elif element_type == InputType.RADIO:
                success = await self._fill_radio(element, page, result.matched_option, options)
            elif element_type == InputType.CHECKBOX:
                success = await self._fill_checkbox(element, page, result.matched_option, options, answer)
            else:
                success = await self._fill_text(element, result.matched_option)
            
            selected = result.matched_option.label if result.matched_option else answer
            
            return success, selected
            
        except Exception as e:
            print(f"⚠️ Fill failed: {e}")
            return False, ""
    
    async def _fill_select(self, element: ElementHandle, option: Option) -> bool:
        if option is None:
            return False
        
        try:
            await element.select_option(value=option.value)
            return True
        except Exception:
            try:
                await element.select_option(label=option.label)
                return True
            except Exception:
                return False
    
    async def _fill_radio(
        self,
        element: ElementHandle,
        page: Page,
        option: Option,
        all_options: List[Option]
    ) -> bool:
        if option is None:
            return False
        
        name = await element.evaluate('el => el.name')
        
        try:
            await page.click(f'input[type="radio"][name="{name}"][value="{option.value}"]')
            return True
        except Exception:
            try:
                await page.click(f'label:has-text("{option.label}")')
                return True
            except Exception:
                return False
    
    async def _fill_checkbox(
        self,
        element: ElementHandle,
        page: Page,
        option: Option,
        all_options: List[Option],
        answer: str
    ) -> bool:
        answer_lower = answer.lower()
        should_check = answer_lower in ['yes', 'true', '1', 'checked', 'agree', 'accept']
        
        try:
            is_checked = await element.evaluate('el => el.checked')
            
            if should_check and not is_checked:
                await element.click()
            elif not should_check and is_checked:
                await element.click()
            
            return True
        except Exception:
            return False
    
    async def _fill_text(self, element: ElementHandle, option: Option) -> bool:
        if option is None:
            return False

        try:
            value = option.value if hasattr(option, 'value') else str(option)
            await element.evaluate('''
                (el, val) => {
                    const proto = el.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value');
                    try {
                        if (nativeSetter && nativeSetter.set) {
                            nativeSetter.set.call(el, val);
                        } else {
                            el.value = val;
                        }
                    } catch (e) {
                        el.value = val;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }
            ''', value)
            return True
        except Exception:
            try:
                await element.fill(option.value if hasattr(option, 'value') else str(option))
                return True
            except Exception:
                return False
    
    async def get_element_info(self, element: ElementHandle, page: Page) -> ElementInfo:
        element_type = await self.detect_element_type(element)
        options = await self.extract_options(element, page)
        
        info = await element.evaluate('''
            el => ({
                tag: el.tagName.toLowerCase(),
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                is_required: el.required || false,
                validation_pattern: el.pattern || null
            })
        ''')
        
        label = await self._find_label(element, page)
        
        return ElementInfo(
            element_type=element_type,
            tag=info['tag'],
            name=info['name'],
            id=info['id'],
            label=label,
            placeholder=info['placeholder'],
            options=options,
            is_required=info['is_required'],
            validation_pattern=info['validation_pattern'],
            element_handle=element
        )
