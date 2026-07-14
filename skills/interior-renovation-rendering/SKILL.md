---
name: interior-renovation-rendering
description: Use when generating or preparing prompts for reference-based interior renovation renderings from an indoor photo, with user-selected room type, decoration style, and color tone. Handles Chinese room types, style descriptions, functional constraints, preservation of the reference architecture, and photorealistic finished renovation image prompts.
---

# Interior Renovation Rendering

Use this skill when the user wants an interior design image generated from a reference indoor photo. The normal product flow is:

1. User uploads one indoor room photo.
2. User selects or provides room type, decoration style, and color tone.
3. Codex creates a finished renovation rendering prompt, then uses image generation if requested and available.

The output should be a polished, buildable, residential renovation effect image that keeps the reference room's architectural shell and camera viewpoint generally consistent.

## Inputs

Required:

- Reference indoor image.
- Room type, such as `客厅`, `卧室`, `厨房`, `卫生间`, `儿童房`, `书房`, `玄关`.
- Decoration style, such as `北欧风`, `原木风`, `现代简约`, `新中式`.

Optional:

- Color tone, such as `暖色调`, `冷色调`, `明亮`, `低饱和`, `深色`, `奶油色`.
- Extra constraints, such as family members, storage needs, pet-friendly, child-safe, keep existing window, or avoid TV.

If a required input is missing and cannot be inferred, ask one concise question. If the user gives a room photo and only one or two controls are missing, use a reasonable mainstream default only when the user asks to proceed directly.

## Style Reference

For supported Chinese styles, load only when needed:

- `references/interior_style_descriptions_cn_0603.json`

Use the matching `style_name` and `style_description` as mandatory design guidance. If the selected style is not in the JSON, use general interior design knowledge and make the style-specific decisions explicit in the prompt.

When using a long style description, do not paste it blindly if a shorter prompt is needed. Extract the visible decisions into:

- palette
- wall, floor, ceiling, door/window finishes
- main furniture forms and materials
- textiles
- lighting
- wall decor
- tabletop decor
- plants
- signature symbols
- style-specific avoid rules

## Room Direction Rules

Map room types by longest or most specific match first. For example, `儿童房` beats `卧室`, and `客餐厅` should become a living-dining combo unless the user chooses only one zone.

- `儿童`, `儿童房`, `儿童卧室`: create a safe children's bedroom with a properly scaled bed, study desk, toy and book storage, rounded furniture, playful but restrained accents, and open floor area for movement.
- `卧室`, `主卧`, `次卧`, `老人房`: create a comfortable bedroom with bed, bedside lighting, wardrobe or storage, curtains, rug, reading or dressing corner when space allows, and clear access around the bed.
- `厨房`: create a practical kitchen with continuous countertop, upper and lower cabinets, sink, cooktop, appliances, task lighting, easy-to-clean materials, and clear working aisle.
- `卫生间`, `浴室`, `洗手间`: create a practical bathroom with realistic vanity, toilet, shower or bathtub area when appropriate, waterproof storage, mirror lighting, non-slip tiles, and believable plumbing positions.
- `客厅`: create a comfortable living room with sofa seating, coffee table, TV or media wall, storage, rug, curtains, accent chair or side table when space allows, and open circulation.
- `餐厅`: create a welcoming dining room with dining table and chairs, pendant or linear light, sideboard or storage, simple table styling, and clear circulation around the table.
- `客餐厅`: create a coherent living-dining room with sofa and media zone, dining table and chairs, balanced lighting for both zones, storage where practical, and continuous circulation between zones.
- `书房`: create a quiet study with desk, ergonomic chair, bookshelves, task lighting, concealed cable management, reading corner when space allows, and clear circulation.
- `阳台`: create a practical balcony with laundry or leisure function as appropriate, waterproof floor, storage cabinet, plants, compact seating, drying or utility area, and clear access to windows or doors.
- `衣帽间`: create a functional walk-in closet with hanging zones, drawers, open and closed storage, full-length mirror, dressing bench or stool, integrated lighting, and clear access to clothing.
- `储物间`: create an organized storage room with shelving, closed cabinets, categorized storage boxes, cleaning tool area, bright practical lighting, and a clear walkway.
- `茶室`: create a calm tea room with tea table, low chairs or cushions, display shelves, warm wood or stone materials, soft lighting, quiet decor, and comfortable circulation.
- `办公室`: create a practical home office or office room with work desk, ergonomic chair, file storage, meeting or guest seating when space allows, task lighting, cable management, and professional atmosphere.
- `阁楼`: create a cozy attic room that uses the sloped ceiling efficiently, with low storage, reading or sleeping nook, warm lighting, soft textiles, and no cramped or blocked circulation.
- `画室`: create an art studio with easel or worktable, material storage, artwork display wall, good natural and task lighting, durable easy-clean flooring, and open working space.
- `娱乐室`, `影音室`: create an entertainment room with media wall or projector, comfortable sofa seating, game or audio equipment storage, acoustic soft furnishings, ambient lighting, and clear circulation.
- `健身房`: create a compact home gym with durable flooring, exercise equipment scaled to the room, mirror or storage wall where appropriate, ventilation, task lighting, and safe open movement space.
- `楼梯间`: create a safe and elegant stair area with handrail, step lighting, wall decor, under-stair storage where appropriate, durable materials, and unobstructed passage.
- `走廊`: create a refined hallway with linear lighting, wall art or end-view decor, slim console or niche storage when width allows, durable flooring, and clear walking width.
- `玄关`: create a practical entryway with shoe cabinet, bench, coat hooks or closet, full-length mirror, key tray, umbrella storage, warm entry lighting, and smooth transition into the home.

For kitchens, bathrooms, balconies, laundry zones, and other wet or utility spaces, translate the selected style into waterproof, heat-resistant, easy-clean finishes and suitable fixtures. Do not force impractical rugs, loose textiles, beds, sofas, or fragile decor into wet or cooking areas.

## Prompt Assembly

Write the final generation prompt in English unless the target image model performs better with Chinese in the current product. Keep user-facing explanations in Chinese if the conversation is Chinese.

Use this prompt structure:

```text
Reference-based interior renovation rendering.
Use the provided indoor photo as the spatial reference. Keep the main room shell, camera viewpoint, major wall planes, door and window locations, ceiling height, floor outline, fixed openings, and overall architectural proportions generally consistent with the reference. Pixel-level alignment is not required; small shifts in window or furniture alignment are acceptable if the finished layout remains believable. Do not add, remove, or relocate major doors, windows, columns, beams, stairs, or fixed openings unless the reference already implies them. Do not change the room into a different architectural space.

Room type: {room_type}.
Decoration style: {style_name}.
Color tone: {color_tone}.
Room-specific functional direction: {room_direction}.

Priority order:
1. Preserve the reference room architecture and camera perspective.
2. Keep the requested room type functional and believable.
3. Make the requested decoration style dominant.
4. Add styling details only when they do not block circulation or core functions.

Style contract:
The following style description is mandatory design guidance. Follow its palette, hard-finish materials, soft furnishing language, furniture forms, lighting fixtures, wall decor, tabletop decor, plants, and signature style symbols. Do not replace it with a generic modern neutral scheme.
<<<
{style_description_or_extracted_style_contract}
>>>

Must visibly include at least five style-specific decisions from the style contract, covering hard finishes, furniture silhouette, textiles, lighting, decor, plants, or signature symbols. The selected color tone should influence the palette and lighting while staying compatible with the style contract.

Transform the rough, old, or unfinished interior into a polished, buildable finished renovation effect image. The requested decoration style must be the dominant visual identity, not a minor accent. Translate the style contract into visible decisions for color palette, wall and floor finishes, ceiling treatment, furniture silhouettes, cabinet or fixture materials, textiles, lighting fixtures, wall art, tabletop decor, plants, and signature style symbols. Arrange furniture around practical functional zones and keep clear circulation paths so doors, windows, cabinetry, appliances, showers, and seating areas remain usable.

The layout should be attractive, residential, and feasible to execute in a real home: avoid empty oversized floors, avoid decorative furniture that blocks movement, keep furniture scale realistic, and make the room feel complete, comfortable, and professionally styled without looking messy.

Avoid generic beige modern staging, hotel-like showroom design, empty minimalist rooms, random luxury elements, style-neutral furniture that ignores the contract, people, text, watermark, distorted perspective, impossible furniture scale, and blocked doors or windows.

Lighting: natural daylight plus layered interior lighting that matches the requested style and color tone.
Rendering quality: photorealistic, clean composition, realistic scale, accurate perspective, high detail, no people, no text, no watermark.
```

## Preflight Checklist

Before generating or returning the prompt, check:

- The room type has a functional direction.
- The style name is represented as the dominant identity, not just small decor.
- Color tone does not contradict the selected style. If it does, adapt gently and state the assumption.
- Wet rooms and kitchens use practical waterproof or easy-clean equivalents.
- The prompt preserves the reference architecture and camera.
- Circulation remains clear and furniture scale is realistic.
- The prompt includes strong negative constraints against generic staging, text, watermark, people, and impossible layouts.

## Output

If the user asks for an image, generate the image directly after assembling the prompt. If generation is unavailable, return the final prompt and mention that it is ready for the image model.

If the user asks for prompt engineering or workflow design, return the improved prompt template, data mapping, or implementation notes instead of generating an image.
