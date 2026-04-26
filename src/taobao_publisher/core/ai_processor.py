"""
AI 处理器
支持：标题优化 / 描述优化 / 规格优化 / 多图分析 / 视频封面分析
"""
import asyncio
import base64
import json
from pathlib import Path
from typing import Optional, Callable
import httpx
from loguru import logger

from taobao_publisher.utils.config import config
from taobao_publisher.core.csv_parser import ProductItem, ProductSpec, SkuItem


class AIProcessor:
    """多提供商 AI 处理器"""

    def _get_api_config(self, for_image: bool = False) -> tuple[str, str, str]:
        provider = config.get("ai", "provider", default="volcano")
        if provider == "volcano":
            if for_image:
                # 使用图片生成专用配置
                return (
                    config.get("ai", "volcano_api_key", default=""),
                    config.get("ai", "volcano_base_url",
                               default="https://ark.cn-beijing.volces.com/api/v3"),
                    config.get("ai", "volcano_image_model", 
                               default="Doubao-Seedream-5.0-lite"),
                )
            else:
                # 使用文本对话配置
                return (
                    config.get("ai", "volcano_api_key", default=""),
                    config.get("ai", "volcano_base_url",
                               default="https://ark.cn-beijing.volces.com/api/v3"),
                    config.get("ai", "volcano_model", default=""),
                )
        elif provider == "openai":
            return (
                config.get("ai", "openai_api_key", default=""),
                config.get("ai", "openai_base_url",
                           default="https://api.openai.com/v1"),
                config.get("ai", "openai_model", default="gpt-4o"),
            )
        else:
            return (
                config.get("ai", "custom_api_key", default=""),
                config.get("ai", "custom_base_url", default=""),
                config.get("ai", "custom_model", default=""),
            )

    async def _chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        api_key, base_url, model = self._get_api_config()
        if not api_key or not model:
            raise ValueError("AI 配置不完整，请在设置中填写 API Key 和 Model")

        # 使用连接池和更短的超时时间
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(90.0, connect=10.0)

        async with httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=True
        ) as client:
            try:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Connection": "close"  # 避免连接池泄漏
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                logger.error(f"AI API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.TimeoutException:
                logger.error("AI API 请求超时")
                raise
            except Exception as e:
                logger.error(f"AI API 请求异常: {e}")
                raise
    
    async def _generate_image(
        self,
        prompt: str,
        model: str = "seedream-4.0-5.0",
        size: str = "1920x1920",
        steps: int = 50,
    ) -> str:
        """使用火山AI生成图片"""
        api_key, base_url, model = self._get_api_config(for_image=True)
        if not api_key:
            raise ValueError("AI 配置不完整，请在设置中填写 API Key")
        
        # 使用连接池和更短的超时时间
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(120.0, connect=10.0)
        
        async with httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=True
        ) as client:
            try:
                # 火山AI图片生成API端点
                image_url = f"{base_url.rstrip('/')}/images/generations"
                
                resp = await client.post(
                    image_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Connection": "close"
                    },
                    json={
                        "model": model,
                        "prompt": prompt,
                        "size": size,
                        "steps": steps,
                        "n": 1,  # 生成1张图片
                    },
                )
                resp.raise_for_status()
                
                # 解析响应，获取图片URL
                result = resp.json()
                if "data" in result and len(result["data"]) > 0:
                    return result["data"][0]["url"]
                else:
                    logger.error(f"图片生成失败: {result}")
                    return ""
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"图片生成API请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.TimeoutException:
                logger.error("图片生成API请求超时")
                raise
            except Exception as e:
                logger.error(f"图片生成API请求异常: {e}")
                raise
    
    async def _download_and_save_image(
        self,
        image_url: str,
        save_path: str,
    ) -> bool:
        """下载并保存图片"""
        try:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            timeout = httpx.Timeout(60.0, connect=10.0)
            
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                follow_redirects=True
            ) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                
                # 保存图片
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                
                logger.info(f"图片已保存到: {save_path}")
                return True
                
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return False

    # ── 图片处理 ────────────────────────────────────────

    async def _image_to_message_part(self, image: str) -> Optional[dict]:
        """
        将图片路径或 URL 转为 OpenAI 兼容的 image_url message part。
        返回 None 表示无法处理。
        """
        if not image:
            return None

        if image.startswith("http://") or image.startswith("https://"):
            return {"type": "image_url", "image_url": {"url": image}}

        # 本地文件
        p = Path(image)
        if not p.exists():
            logger.warning(f"图片文件不存在: {image}")
            return None

        try:
            with open(p, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            ext = p.suffix.lower().lstrip(".")
            mime = {"jpg": "jpeg", "jpeg": "jpeg",
                    "png": "png", "webp": "webp",
                    "gif": "gif"}.get(ext, "jpeg")
            return {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{data}"},
            }
        except Exception as e:
            logger.warning(f"读取图片失败 [{image}]: {e}")
            return None

    async def analyze_images(
        self,
        images: list[str],
        max_images: int = 3,
        context: str = "",
        generate_new_images: bool = False,
        output_dir: str = ""
    ) -> str:
        """
        分析多张图片，返回综合描述。
        max_images：最多发送给 AI 的图片数量（避免 token 超限）
        generate_new_images：是否生成新图片
        output_dir：生成图片的保存目录
        """
        # 过滤有效图片
        valid = [img for img in images if img][:max_images]
        if not valid:
            return ""

        parts: list[dict] = []
        for img in valid:
            part = await self._image_to_message_part(img)
            if part:
                parts.append(part)

        if not parts:
            return ""

        prompt_text = (
            f"【图片后期处理任务】\n"
            f"我会发给你对应数量的图片，需要对每张图片进行后期处理优化。\n"
            f"{'背景信息：' + context if context else ''}\n\n"
            f"【核心要求】\n"
            f"这不是重新生成图片的任务，而是对原图进行后期处理。\n"
            f"必须严格保持原图的所有元素完全一致，包括：\n"
            f"- 产品的外观、形状、颜色、图案、文字（每个字、每个图案都必须完全相同）\n"
            f"- 道具的种类、位置、摆放方式（每个道具的位置、角度都不能改变）\n"
            f"- 场景的布局、背景、环境元素（所有背景元素必须保持原样）\n"
            f"- 所有细节和特征（包括纹理、质感、光影细节等）\n\n"
            f"【像素级保持一致】\n"
            f"原图的每个元素都必须在处理后保持：\n"
            f"- 相同的外观和形状\n"
            f"- 相同的颜色和图案\n"
            f"- 相同的文字内容和字体\n"
            f"- 相对位置关系不变\n"
            f"- 整体构图不变\n"
            f"- 只改变光影、画质、色彩等后期效果\n\n"
            f"【后期处理范围】\n"
            f"只允许改变以下内容：\n"
            f"- 光影效果（调整光线方向、强度、阴影）\n"
            f"- 画质增强（提高清晰度、锐度、降噪）\n"
            f"- 色彩调性（调整饱和度、色调、对比度）\n"
            f"- 拍摄角度（微调不超过5度）\n"
            f"- 道具摆放（仅微调角度，不改变位置）\n\n"
            f"【禁止事项】\n"
            f"绝对禁止：\n"
            f"- 改变产品的外观、形状、颜色、图案、文字\n"
            f"- 增加或删除任何元素\n"
            f"- 改变场景布局\n"
            f"- 改变道具的种类和位置\n"
            f"- 重新生成任何内容\n"
            f"- 任何可能导致原图元素改变的操作\n\n"
            f"【风格要求】\n"
            f"- 高级简约家居场景\n"
            f"- 专业电商摄影风格\n"
            f"- 无重复元素\n"
            f"- 无侵权风险\n\n"
            f"【重要提醒】\n"
            f"如果无法确保原图所有元素像素级保持一致，请明确说明，不要生成图片。\n"
        )
        
        if generate_new_images and output_dir:
            # 如果需要生成新图片，添加生成提示
            prompt_text += (
                "请为每张图片生成后期处理描述，格式如下：\n"
                "图片1描述：[原图所有元素的详细描述]\n"
                "图片2描述：[原图所有元素的详细描述]\n"
                "...\n\n"
                "每个描述必须包含：\n"
                "1. 原图所有元素的详细描述（产品、道具、场景等）\n"
                "   - 产品的外观、形状、颜色、图案、文字\n"
                "   - 道具的种类、位置、摆放方式\n"
                "   - 场景的布局、背景、环境元素\n"
                "   - 所有细节和特征\n\n"
                "2. 后期处理的具体方案（光影、画质、色彩等）\n"
                "   - 使用直观的视觉描述，如'柔和自然光'、'温暖色调'等\n"
                "   - 避免使用具体的技术参数（如+30%、0.3EV等）\n"
                "   - 重点描述最终视觉效果而非处理过程\n\n"
                "3. 明确说明不改变任何原有元素\n"
                "   - 强调100%保留原图所有元素\n"
                "   - 只改变光影、画质、色彩等后期效果\n\n"
                "4. 适合用于图片后期处理的详细指令\n"
                "   - 使用自然语言描述期望的视觉效果\n"
                "   - 避免分步骤的技术指令\n"
                "   - 强调整体效果而非具体参数\n\n"
                "重要提示：\n"
                "- 这是后期处理任务，不是重新生成图片\n"
                "- 必须严格保留原图所有元素\n"
                "- 只改变光影、画质、色彩等后期效果\n"
                "- 避免使用具体技术参数，使用视觉描述\n"
                "- 如果无法确保原图所有元素保留不变，请明确说明"
            )
        else:
            # 只分析不生成
            prompt_text += "请为每张图片提供后期处理建议，输出简洁，每张图片不超过100字："
        
        parts.append({"type": "text", "text": prompt_text})

        try:
            result = await self._chat(
                messages=[{"role": "user", "content": parts}],
                max_tokens=800 if generate_new_images else 300,
                temperature=0.5,
            )
            logger.debug(f"图片分析完成（{len(parts) - 1} 张）: {result[:60]}...")
            
            # 如果需要生成新图片，解析结果并生成图片
            if generate_new_images and output_dir:
                await self._generate_images_from_descriptions(
                    valid, result, output_dir, context
                )
            
            return result.strip()
        except Exception as e:
            logger.warning(f"图片分析失败: {e}")
            return ""
    
    async def _generate_images_from_descriptions(
        self,
        original_images: list[str],
        descriptions: str,
        output_dir: str,
        context: str = ""
    ):
        """
        根据图片描述生成新图片
        """
        from pathlib import Path
        import re
        import base64
        from datetime import datetime
        
        # 确保输出目录存在
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 解析每个图片的描述
        image_desc_pattern = r"图片(\d+)描述：([\s\S]*?)(?=图片\d+描述：|$)"
        matches = re.findall(image_desc_pattern, descriptions)
        
        if not matches:
            logger.warning("未能解析图片描述，跳过图片生成")
            return
        
        # 为每个描述生成图片
        for i, (img_num, desc) in enumerate(matches):
            if i >= len(original_images):
                break
                
            try:
                # 构建图片生成提示
                gen_prompt = (
                    f"【图片后期处理任务】\n\n"
                    f"原始商品：{context or '未知商品'}\n\n"
                    f"原图元素描述：\n{desc.strip()}\n\n"
                    f"【核心要求】\n"
                    f"这不是重新生成图片的任务，而是对原图进行后期处理。\n"
                    f"必须严格保持原图的所有元素完全一致，包括：\n"
                    f"- 产品的外观、形状、颜色、图案、文字（每个字、每个图案都必须完全相同）\n"
                    f"- 道具的种类、位置、摆放方式（每个道具的位置、角度都不能改变）\n"
                    f"- 场景的布局、背景、环境元素（所有背景元素必须保持原样）\n"
                    f"- 所有细节和特征（包括纹理、质感、光影细节等）\n\n"
                    f"【像素级保持一致】\n"
                    f"原图的每个元素都必须在处理后保持：\n"
                    f"- 相同的外观和形状\n"
                    f"- 相同的颜色和图案\n"
                    f"- 相同的文字内容和字体\n"
                    f"- 相对位置关系不变\n"
                    f"- 整体构图不变\n"
                    f"- 只改变光影、画质、色彩等后期效果\n\n"
                    f"【后期处理原则】\n"
                    f"1. 只改变光影、画质、色彩等后期效果\n"
                    f"2. 使用直观的视觉描述，如'柔和自然光'、'温暖色调'等\n"
                    f"3. 避免使用具体的技术参数（如+30%、0.3EV等）\n"
                    f"4. 重点描述最终视觉效果而非处理过程\n"
                    f"5. 拍摄角度微调不超过5度\n"
                    f"6. 道具摆放仅微调角度，不改变位置\n\n"
                    f"【禁止事项】\n"
                    f"绝对禁止：\n"
                    f"- 改变产品的外观、形状、颜色、图案、文字\n"
                    f"- 增加或删除任何元素\n"
                    f"- 改变场景布局\n"
                    f"- 改变道具的种类和位置\n"
                    f"- 重新生成任何内容\n"
                    f"- 使用具体技术参数\n"
                    f"- 任何可能导致原图元素改变的操作\n\n"
                    f"【风格要求】\n"
                    f"- 高级简约家居场景\n"
                    f"- 专业电商摄影风格\n"
                    f"- 无重复元素\n"
                    f"- 无侵权风险\n\n"
                    f"【重要提示】\n"
                    f"- 必须严格保留原图所有元素\n"
                    f"- 只改变光影、画质、色彩等后期效果\n"
                    f"- 使用视觉描述而非技术参数\n"
                    f"- 如果无法确保原图所有元素像素级保持一致，请明确说明，不要生成图片\n\n"
                    f"【特别强调】\n"
                    f"保留产品和场景结构，重新渲染光影效果，微调拍摄角度，增强画质清晰度，微调道具摆放，优化色彩调性，高级简约家居场景，专业电商摄影，无重复元素，无侵权风险，确保不改变图片本身，卖的就是图片，改变了图片本身，主观判定就是不对的，确保不要改变图片的原有内容，如果无法确保图片不变，还是不够，确保原图的所有元素都保留不变，只改变影视后期处理"
                )
                
                # 调用火山AI图片生成API
                try:
                    logger.info(f"正在生成图片 {img_num}...")
                    logger.debug(f"图片生成提示: {gen_prompt[:100]}...")
                    
                    # 生成图片
                    image_url = await self._generate_image(gen_prompt)
                    
                    if image_url:
                        # 下载并保存图片
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        image_filename = f"generated_image_{int(img_num):02d}_{timestamp}.jpg"
                        image_path = output_path / image_filename
                        
                        success = await self._download_and_save_image(image_url, str(image_path))
                        
                        if success:
                            # 保存描述和生成信息到文件
                            desc_filename = f"image_{int(img_num):02d}_{timestamp}.txt"
                            desc_path = output_path / desc_filename
                            
                            with open(desc_path, 'w', encoding='utf-8') as f:
                                f.write(f"原始图片: {original_images[i]}\n\n")
                                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                                f.write(f"优化描述:\n{desc.strip()}\n\n")
                                f.write(f"生成提示:\n{gen_prompt}\n\n")
                                f.write(f"生成图片URL: {image_url}\n\n")
                                f.write(f"本地保存路径: {image_path}")
                            
                            logger.info(f"图片 {img_num} 已生成并保存到: {image_path}")
                            logger.info(f"图片 {img_num} 描述已保存到: {desc_path}")
                        else:
                            logger.error(f"下载图片 {img_num} 失败")
                    else:
                        logger.error(f"生成图片 {img_num} 失败: 未获取到图片URL")
                    
                except Exception as e:
                    logger.error(f"生成图片 {img_num} 失败: {e}")
                    
            except Exception as e:
                logger.error(f"处理图片 {img_num} 失败: {e}")

    async def analyze_video_cover(self, video_url: str) -> str:
        """
        分析视频封面（从视频 URL 提取封面帧进行分析）。
        注意：直接分析视频 URL 需要模型支持视频，否则降级为文本分析。
        """
        if not video_url:
            return ""

        # 如果是淘宝视频链接，尝试提取封面
        cover_url = self._extract_video_cover_url(video_url)
        if cover_url:
            return await self.analyze_images([cover_url], max_images=1,
                                             context="商品视频封面")

        # 降级：仅根据 URL 描述
        logger.debug(f"视频无封面可提取: {video_url[:40]}...")
        return ""

    def _extract_video_cover_url(self, video_url: str) -> str:
        """
        尝试从视频 URL 推导封面图 URL。
        淘宝视频格式举例：
          https://video.taobao.com/xxx.mp4 → cover可能在同路径
        """
        # mp4 文件尝试 OSS 封面
        if ".mp4" in video_url:
            cover = re.sub(r"\.mp4.*$", "_cover.jpg", video_url)
            if cover != video_url:
                return cover
        return ""

    # ── 内容优化 ────────────────────────────────────────

    async def optimize_title(
        self,
        product: ProductItem,
        image_analysis: str = "",
    ) -> str:
        """优化商品标题（结合图片分析结果）"""
        if not config.get("ai", "optimize_title", default=True):
            return product.title

        style = config.get("ai", "title_style", default="电商爆款风格")

        # 构建属性摘要
        attr_summary = "；".join(f"{k}:{v}" for k, v in list(product.attributes.items())[:5])
        spec_summary = "、".join(s.name for s in product.specs)

        prompt = f"""你是资深淘宝电商运营专家，请优化以下商品标题。

【原始标题】{product.title}
【类目ID】{product.category_id or "未知"}
【一口价】{product.price} 元
【规格维度】{spec_summary or "无"}
【商品属性】{attr_summary or "无"}
【图片描述】{image_analysis or "无"}
【风格要求】{style}

【优化要求】
1. 标题总字数 ≤ 30 字（淘宝限制）
2. 前段放核心关键词（搜索权重最高）
3. 包含材质 / 功能 / 使用场景等卖点
4. 符合淘宝规范，不含违禁词（如"第一""最"等极限词）
5. 自然流畅，避免堆砌关键词

直接输出优化后的标题，不要任何解释："""

        try:
            result = await self._chat(
                [{"role": "user", "content": prompt}],
                temperature=0.8, max_tokens=80,
            )
            title = result.strip().strip('"').strip("'").replace("\n", "")
            logger.info(f"标题优化: [{product.title[:15]}] → [{title[:15]}]")
            return title
        except Exception as e:
            logger.warning(f"标题优化失败: {e}")
            return product.title

    async def optimize_description(
        self,
        product: ProductItem,
        image_analysis: str = "",
    ) -> str:
        """优化商品详情描述（结合图片分析）"""
        if not config.get("ai", "optimize_description", default=True):
            return product.description

        style = config.get("ai", "description_style", default="专业详细")

        specs_text = "\n".join(
            f"  {s.name}: {', '.join(s.values)}" for s in product.specs
        )
        attrs_text = "\n".join(
            f"  {k}: {v}" for k, v in product.attributes.items()
        )

        # SKU 价格区间
        if product.sku_list:
            prices = [s.price for s in product.sku_list if s.price > 0]
            price_range = (f"¥{min(prices):.2f} ~ ¥{max(prices):.2f}"
                           if prices else f"¥{product.price:.2f}")
        else:
            price_range = f"¥{product.price:.2f}"

        prompt = f"""你是专业淘宝电商文案策划师，请生成高转化率的商品详情描述。

【商品信息】
- 标题：{product.display_title}
- 价格：{price_range}
- 规格：
{specs_text or "  无"}
- 属性：
{attrs_text or "  无"}
- 原始描述：{product.description or "无"}
- 图片分析：{image_analysis or "无"}

【文案风格】{style}

【输出要求】
1. 结构：产品亮点 → 核心功能 → 规格参数 → 使用场景 → 品质保证
2. 字数：200 ~ 500 字
3. 善用换行分段和 emoji，视觉层次清晰
4. 突出差异化卖点，促进转化
5. 不包含 HTML 标签

直接输出文案内容："""

        try:
            result = await self._chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7, max_tokens=900,
            )
            logger.info(f"描述优化完成，字数: {len(result)}")
            return result.strip()
        except Exception as e:
            logger.warning(f"描述优化失败: {e}")
            return product.description

    async def optimize_specs(self, product: ProductItem) -> list[ProductSpec]:
        """规格名称 & 值规范化"""
        if not config.get("ai", "optimize_specs", default=True) or not product.specs:
            return product.specs

        specs_json = json.dumps(
            [{"name": s.name, "values": s.values} for s in product.specs],
            ensure_ascii=False,
        )

        prompt = f"""你是淘宝电商规格标准化专家，请规范以下商品规格信息。

商品标题：{product.display_title}
原始规格：{specs_json}

【规范要求】
1. 规格名称使用淘宝标准命名（如"颜色分类"而非"颜色"）
2. 规格值描述清晰准确，修正错别字
3. 保持原有数据结构，不删减
4. 颜色类规格建议加色号（如"深红色#8B0000"）

以 JSON 格式返回，格式：[{{"name":"规格名","values":["值1","值2"]}}]
只输出 JSON，不要其他文字："""

        try:
            raw = await self._chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=600,
            )
            # 提取 JSON
            raw = raw.strip()
            if "```" in raw:  
                raw = re.sub(r"```(?:json)?", "", raw).strip()

            data = json.loads(raw)
            optimized = [
                ProductSpec(name=s["name"], values=s["values"])
                for s in data
            ]
            logger.info(f"规格优化完成: {len(optimized)} 个维度")
            return optimized
        except Exception as e:
            logger.warning(f"规格优化失败（保持原规格）: {e}")
            return product.specs

    async def suggest_sku_prices(self, product: ProductItem) -> list[SkuItem]:
        """
        对 SKU 价格进行智能建议（差异化定价）。
        仅在 SKU 价格全为 0 时触发。
        """
        if not product.sku_list:
            return product.sku_list

        all_zero = all(s.price == 0 for s in product.sku_list)
        if not all_zero or product.price == 0:
            return product.sku_list

        skus_json = json.dumps(
            [{"combo": s.combo_str, "stock": s.stock} for s in product.sku_list],
            ensure_ascii=False,
        )

        prompt = f"""根据商品信息为各 SKU 建议合理价格。

商品：{product.display_title}
一口价参考：{product.price} 元（若为0则无参考）
SKU 列表：{skus_json}

【定价原则】
- 基础款定价偏低，特殊规格（如大尺寸、深色）可适当加价
- 价格波动在 ±30% 合理范围内
- 保留两位小数

JSON 格式返回：[{{"combo":"规格组合字符串","price":价格}}]
只输出 JSON："""

        try:
            raw = await self._chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=500,
            )
            raw = raw.strip()
            if "```" in raw:  
                raw = re.sub(r"```(?:json)?", "", raw).strip()

            data = json.loads(raw)
            price_map = {d["combo"]: float(d["price"]) for d in data}

            for sku in product.sku_list:
                if sku.combo_str in price_map:
                    sku.price = price_map[sku.combo_str]

            logger.info(f"SKU 价格建议完成: {len(price_map)} 条")
        except Exception as e:
            logger.warning(f"SKU 定价建议失败: {e}")

        return product.sku_list

    # ── 全量处理 ────────────────────────────────────────

    async def process_product(
        self,
        product: ProductItem,
        progress_callback: Optional[Callable[[str], None]] = None,
        generate_images: bool = False,
        image_output_dir: str = "",
    ) -> ProductItem:
        """对单个商品执行全量 AI 优化"""

        def cb(msg: str):
            if progress_callback:
                progress_callback(msg)
            logger.info(msg)

        cb(f"🤖 开始处理: {product.title[:25]}...")

        # ── Step 1: 分析主图───────────────────────
        image_analysis = ""
        if product.main_images:
            if generate_images and image_output_dir:
                cb(f"🎨 分析并生成新图片（{len(product.main_images)} 张）...")
                # 创建该商品的图片输出目录
                from pathlib import Path
                import os
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", product.title[:30])
                product_img_dir = os.path.join(image_output_dir, safe_title)
                Path(product_img_dir).mkdir(parents=True, exist_ok=True)
                
                image_analysis = await self.analyze_images(
                    product.main_images,
                    max_images=len(product.main_images),
                    context=product.title,
                    generate_new_images=True,
                    output_dir=product_img_dir,
                )
            else:
                cb(f"🖼️ 分析主图（{len(product.main_images)} 张）...")
                image_analysis = await self.analyze_images(
                    product.main_images,
                    max_images=len(product.main_images),
                    context=product.title,
                )
            product.ai_image_analysis = image_analysis

        # ── Step 2: 分析视频封面（如有）────────────────────
        video_analysis = ""
        if product.videos and not image_analysis:
            cb("🎬 分析视频封面...")
            video_analysis = await self.analyze_video_cover(product.videos[0])

        combined_analysis = image_analysis or video_analysis

        # ── Step 3: 优化标题 ────────────────────────────
        cb("✍️ 优化商品标题...")
        product.ai_title = await self.optimize_title(product, combined_analysis)

        # ── Step 4: 优化规格 ────────────────────────────
        if product.specs:
            cb("📋 规范化商品规格...")
            product.ai_specs = await self.optimize_specs(product)

        # ── Step 5: 优化描述 ────────────────────────────
        cb("📝 生成商品详情描述...")
        product.ai_description = await self.optimize_description(
            product, combined_analysis
        )

        # ── Step 6: SKU 定价建议 ────────────────────────
        if product.sku_list:
            cb("💰 SKU 差异化定价建议...")
            product.sku_list = await self.suggest_sku_prices(product)

        product.status = "ai_done"
        cb(f"✅ AI 处理完成: {product.ai_title[:25]}...")
        return product

    async def process_batch(
        self,
        products: list[ProductItem],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        concurrency: int = 1,
        generate_images: bool = False,
        image_output_dir: str = "",
    ) -> list[ProductItem]:
        """批量处理（concurrency=1 避免 API 限速）"""
        total = len(products)

        if concurrency <= 1:
            for i, product in enumerate(products):
                try:
                    def _cb(msg, idx=i):
                        if progress_callback:
                            progress_callback(idx + 1, total, msg)
                    await self.process_product(
                        product, 
                        _cb, 
                        generate_images=generate_images, 
                        image_output_dir=image_output_dir
                    )
                    await asyncio.sleep(0.8)
                except Exception as e:
                    product.status = "ai_error"
                    product.error_msg = str(e)
                    logger.error(f"商品 {i + 1} 处理失败: {e}")
        else:
            # 并发处理
            sem = asyncio.Semaphore(concurrency)
            async def _process_one(i: int, p: ProductItem):
                async with sem:
                    try:
                        def _cb(msg):
                            if progress_callback:
                                progress_callback(i + 1, total, msg)
                        await self.process_product(
                            p, 
                            _cb, 
                            generate_images=generate_images, 
                            image_output_dir=image_output_dir
                        )
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        p.status = "ai_error"
                        p.error_msg = str(e)

            await asyncio.gather(*[_process_one(i, p) for i, p in enumerate(products)])

        return products

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self._chat(
                [{"role": "user", "content": "请回复：连接成功"}],
                max_tokens=20,
            )
            return True, f"✅ 连接成功：{result[:40]}"
        except Exception as e:
            return False, f"❌ 连接失败：{e}"
    
    async def save_all_ai_results(self, products: list[ProductItem], output_dir: str) -> str:
        """保存所有AI处理过的内容到指定目录"""
        from pathlib import Path
        from datetime import datetime
        import os
        import json
        
        # 确保输出目录存在
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 创建汇总文件
        summary_file = output_path / f"AI处理汇总_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        # 创建详细数据文件夹
        details_dir = output_path / f"商品详情_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        details_dir.mkdir(exist_ok=True)
        
        # 统计信息
        total_products = len(products)
        ai_processed = sum(1 for p in products if p.status == "ai_done")
        ai_failed = sum(1 for p in products if p.status == "ai_error")
        
        try:
            # 写入汇总文件
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"{'='*80}\n")
                f.write(f"淘宝商品AI处理结果汇总\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*80}\n\n")
                
                f.write(f"【统计信息】\n")
                f.write(f"总商品数: {total_products}\n")
                f.write(f"AI处理成功: {ai_processed}\n")
                f.write(f"AI处理失败: {ai_failed}\n")
                f.write(f"成功率: {ai_processed/total_products*100:.1f}%\n\n")
                
                # 商品列表
                f.write(f"【商品列表】\n")
                for i, p in enumerate(products, 1):
                    status_icon = "✅" if p.status == "ai_done" else "❌" if p.status == "ai_error" else "⏳"
                    f.write(f"{i:3d}. {status_icon} {p.display_title}\n")
                
                f.write(f"\n{'='*80}\n")
                f.write(f"详细内容请查看文件夹: {details_dir.name}\n")
                f.write(f"{'='*80}\n")
            
            # 为每个商品创建详细文件
            for i, p in enumerate(products, 1):
                # 只处理有AI结果的商品
                if not (p.ai_title or p.ai_description or p.ai_specs or p.ai_image_analysis):
                    # 仍然创建文件，但标记为未处理
                    with open(details_dir / f"{i:03d}_{p.title[:20]}.txt", 'w', encoding='utf-8') as f:
                        f.write(f"商品: {p.title}\n")
                        f.write(f"状态: 未进行AI处理\n")
                    continue
                
                # 创建商品详细文件
                with open(details_dir / f"{i:03d}_{p.title[:20]}.txt", 'w', encoding='utf-8') as f:
                    f.write(f"{'='*60}\n")
                    f.write(f"商品AI优化结果\n")
                    f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"{'='*60}\n\n")
                    
                    # 基本信息
                    f.write(f"【基本信息】\n")
                    f.write(f"原始标题: {p.title}\n")
                    if p.ai_title:
                        f.write(f"AI优化标题: {p.ai_title}\n")
                    f.write(f"类目: {p.category_id or '未填写'}\n")
                    f.write(f"价格: ¥{p.price:.2f}\n")
                    f.write(f"库存: {p.stock}\n")
                    f.write(f"\n")
                    
                    # 描述
                    f.write(f"【商品描述】\n")
                    f.write(f"原始描述:\n{p.description or '无'}\n\n")
                    if p.ai_description:
                        f.write(f"AI优化描述:\n{p.ai_description}\n\n")
                    
                    # 规格
                    f.write(f"【规格信息】\n")
                    if p.specs:
                        f.write(f"原始规格:\n")
                        for spec in p.specs:
                            f.write(f"  {spec.name}: {', '.join(spec.values)}\n")
                        f.write(f"\n")
                    
                    if p.ai_specs:
                        f.write(f"AI优化规格:\n")
                        for spec in p.ai_specs:
                            f.write(f"  {spec.name}: {', '.join(spec.values)}\n")
                        f.write(f"\n")
                    
                    # SKU
                    if p.sku_list:
                        f.write(f"【SKU列表】\n")
                        for sku in p.sku_list:
                            f.write(f"  {sku.combo_str}: ¥{sku.price:.2f} (库存: {sku.stock})\n")
                        f.write(f"\n")
                    
                    # 属性
                    if p.attributes:
                        f.write(f"【商品属性】\n")
                        for k, v in p.attributes.items():
                            f.write(f"  {k}: {v}\n")
                        f.write(f"\n")
                    
                    # 图片分析
                    if p.ai_image_analysis:
                        f.write(f"【图片分析】\n")
                        f.write(f"{p.ai_image_analysis}\n\n")
                    
                    f.write(f"{'='*60}\n")
                
                # 创建JSON格式的数据文件，方便程序读取
                product_data = {
                    "title": p.title,
                    "ai_title": p.ai_title or "",
                    "category_id": p.category_id or "",
                    "price": p.price,
                    "stock": p.stock,
                    "description": p.description or "",
                    "ai_description": p.ai_description or "",
                    "attributes": p.attributes,
                    "ai_image_analysis": p.ai_image_analysis or "",
                    "specs": [{"name": s.name, "values": s.values} for s in p.specs],
                    "ai_specs": [{"name": s.name, "values": s.values} for s in p.ai_specs],
                    "sku_list": [{"combo": s.combo_str, "price": s.price, "stock": s.stock} for s in p.sku_list],
                    "status": p.status,
                    "main_images": p.main_images,
                    "detail_images": p.detail_images,
                    "videos": p.videos
                }
                
                with open(details_dir / f"{i:03d}_{p.title[:20]}.json", 'w', encoding='utf-8') as f:
                    json.dump(product_data, f, ensure_ascii=False, indent=2)
            
            return str(summary_file)
        except Exception as e:
            logger.error(f"保存AI处理结果失败: {e}")
            raise


# ── 补充缺失的 import ──────────────────────────
import re