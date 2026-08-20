-- 插入测试用户，对应 Android 客户端硬编码的 user_id=1
INSERT INTO users (id, name, age, profile)
VALUES (1, '测试老人', 75, '{"note": "P1 联调测试用户"}'::json)
ON CONFLICT (id) DO NOTHING;
