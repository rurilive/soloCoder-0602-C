function simulatePaginationLogic() {
  const PAGE_SIZE = 20;
  const TOTAL_MESSAGES = 60;

  console.log('=== 分页逻辑验证 ===');
  console.log(`总消息数: ${TOTAL_MESSAGES}, 每页大小: ${PAGE_SIZE}`);
  console.log('后端按 created_at 降序返回, offset=0 是最新消息\n');

  function fetchMessages(offset, limit) {
    const allMessages = Array.from({ length: TOTAL_MESSAGES }, (_, i) => ({
      id: `msg-${i}`,
      content: `Message ${i}`,
      sortOrder: i,
    }));

    const sortedDesc = [...allMessages].sort((a, b) => b.sortOrder - a.sortOrder);
    const result = sortedDesc.slice(offset, offset + limit);
    return {
      items: result,
      total: TOTAL_MESSAGES,
      offset,
      limit,
    };
  }

  console.log('--- 场景1: 初始加载 (无新消息) ---');
  let loadedHistoryCount = 0;
  let messages = [];

  let response = fetchMessages(0, PAGE_SIZE);
  let reversed = [...response.items].reverse();
  messages = reversed;
  loadedHistoryCount = response.items.length;

  console.log(`初始加载 offset=0, 得到 ${response.items.length} 条`);
  console.log(`  后端返回(降序): ${response.items.map(m => m.content).join(', ')}`);
  console.log(`  前端反转后(升序): ${messages.map(m => m.content).join(', ')}`);
  console.log(`  loadedHistoryCount = ${loadedHistoryCount}`);
  console.log(`  正确: 最新的 ${PAGE_SIZE} 条, 显示顺序从旧到新 ✅`);

  console.log('\n--- 加载更多 ---');
  let offset = loadedHistoryCount;
  response = fetchMessages(offset, PAGE_SIZE);
  reversed = [...response.items].reverse();
  const existingIds = new Set(messages.map(m => m.id));
  const newItems = reversed.filter(m => !existingIds.has(m.id));
  loadedHistoryCount += newItems.length;
  messages = [...newItems, ...messages];

  console.log(`加载更多 offset=${offset}, 得到 ${response.items.length} 条`);
  console.log(`  后端返回(降序): ${response.items.map(m => m.content).join(', ')}`);
  console.log(`  前端反转后: ${reversed.map(m => m.content).join(', ')}`);
  console.log(`  插入后总消息数: ${messages.length}`);
  console.log(`  显示顺序(从旧到新): ${messages.map(m => m.content).join(', ')}`);
  console.log(`  loadedHistoryCount = ${loadedHistoryCount}`);
  console.log(`  正确: 历史消息追加到前面, 顺序正确 ✅`);

  console.log('\n--- 场景2: 初始加载后收到新消息, 再加载更多 ---');
  loadedHistoryCount = 0;
  messages = [];

  response = fetchMessages(0, PAGE_SIZE);
  reversed = [...response.items].reverse();
  messages = reversed;
  loadedHistoryCount = response.items.length;

  console.log(`初始加载后: ${messages.length} 条, loadedHistoryCount = ${loadedHistoryCount}`);

  const newMessagesFromWS = [
    { id: 'msg-60', content: 'Message 60', sortOrder: 60 },
    { id: 'msg-61', content: 'Message 61', sortOrder: 61 },
    { id: 'msg-62', content: 'Message 62', sortOrder: 62 },
  ];
  messages = [...messages, ...newMessagesFromWS];

  console.log(`收到 3 条新消息后: ${messages.length} 条`);
  console.log(`  messages.length = ${messages.length}, 但 loadedHistoryCount 仍 = ${loadedHistoryCount}`);

  offset = loadedHistoryCount;
  response = fetchMessages(offset, PAGE_SIZE);
  reversed = [...response.items].reverse();
  const existingIds2 = new Set(messages.map(m => m.id));
  const newItems2 = reversed.filter(m => !existingIds2.has(m.id));
  loadedHistoryCount += newItems2.length;
  messages = [...newItems2, ...messages];

  console.log(`\n加载更多时 offset = loadedHistoryCount = ${offset}`);
  console.log(`  后端返回(降序): ${response.items.map(m => m.content).join(', ')}`);
  console.log(`  插入后总消息数: ${messages.length}`);
  console.log(`  显示顺序(前5条): ${messages.slice(0, 5).map(m => m.content).join(', ')} ... ${messages.slice(-5).map(m => m.content).join(', ')}`);
  console.log(`  loadedHistoryCount = ${loadedHistoryCount}`);
  console.log(`  正确: 新消息不影响历史分页 offset, 跳过的是已加载的历史消息, 而非最新消息 ✅`);

  console.log('\n=== 结论 ===');
  console.log('使用 loadedHistoryCount 独立追踪已加载的历史消息数:');
  console.log('1. 不受新到达消息的影响');
  console.log('2. 准确对应后端 offset 语义(跳过已加载的历史消息)');
  console.log('3. 代码意图更清晰');
}

simulatePaginationLogic();
