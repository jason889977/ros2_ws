(() => {
  const template = document.getElementById('dashboard-template');
  document.getElementById('app').replaceChildren(template.content.cloneNode(true));

  const state = { status: {}, scans: [], events: [], diagnostics: [], filter: 'all', live: false, wsOnline: false, lastData: 0, calibration: {}, handeye: {} };
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const levelName = value => ['正常', '警告', '错误', '过期'][Math.min(Number(value) || 0, 3)];
  const levelClass = value => Number(value) === 0 ? 'ok' : Number(value) === 1 ? 'warn' : 'error';
  const formatTime = value => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--';
  const get = async url => { const response = await fetch(url); if (!response.ok) throw Error(response.status); return response.json(); };
  const isStale = item => item?.timestamp ? (Date.now() / 1000 - Number(item.timestamp) > 15) : false;
  const streamUrl = () => '/api/camera/stream';
  const snapshotUrl = () => `/api/camera/image?t=${Date.now()}`;
  const calibrationImageUrl = () => `/api/calibration/preview?t=${Date.now()}`;
  const handeyeImageUrl = () => `/api/handeye/preview?t=${Date.now()}`;
  const POSE_GUIDE = [
    { title: '正对居中', hint: '板面正对镜头，约占画面一半' },
    { title: '靠近拍摄', hint: '板占画面 2/3 以上，保持清晰' },
    { title: '远离拍摄', hint: '板占画面 1/3 左右' },
    { title: '移到左上', hint: '板贴近画面左上角' },
    { title: '移到右上', hint: '板贴近画面右上角' },
    { title: '移到左下', hint: '板贴近画面左下角' },
    { title: '移到右下', hint: '板贴近画面右下角' },
    { title: '倾斜视角', hint: '左右或上下倾斜 30°~45°' },
  ];
  const HANDEYE_POSE_GUIDE = [
    { title: '初始姿态', hint: '机械臂到初始位置，AprilTag 清晰可见，记录第一组' },
    { title: 'X 轴正向平移', hint: '仅沿 X 正方向平移 30-50mm，保持姿态不变' },
    { title: 'Y 轴正向平移', hint: '仅沿 Y 正方向平移 30-50mm，保持姿态不变' },
    { title: 'Z 轴正向平移', hint: '仅沿 Z 正方向平移 30-50mm，保持姿态不变' },
    { title: 'Roll 轴 +15°', hint: '绕 X 轴旋转约 15°，避免纯平移无旋转' },
    { title: 'Pitch 轴 +15°', hint: '绕 Y 轴旋转约 15°，旋转角度需有明显变化' },
    { title: 'Yaw 轴 +15°', hint: '绕 Z 轴旋转约 15°，保持标签始终可见' },
    { title: '混合姿态 1', hint: '大幅平移 + 复合旋转，标签完整出现在画面中' },
    { title: '混合姿态 2', hint: '再变化一组合成姿态，与之前姿态跨度要大' },
    { title: '姿态组合收尾', hint: '最后一组需覆盖 X/Y/Z 三轴平移与旋转跨度' },
  ];
  const CALIB_PHASES = { idle: '未开始', queued: '排队中', collecting: '采集准备', detecting: '检测 AprilGrid', calibrating: '计算内参', done: '标定完成', failed: '标定失败', cancelling: '取消中' };
  const RUNNING_PHASES = ['queued', 'collecting', 'detecting', 'calibrating', 'cancelling'];
  const HANDEYE_PHASES = { idle: '未开始', collecting: '采集中', solving: '求解中', done: '完成', failed: '失败' };
  const HANDEYE_RUNNING = { solving: true };

  function setConnection(online) {
    state.wsOnline = online;
    $('connectionDot').className = online ? 'ok' : 'bad';
    $('connectionText').textContent = online ? '数据在线' : '数据断开';
    $('connectionBanner').hidden = online;
  }
  function renderStatus(status) {
    if (!status?.camera_id) return;
    state.status = status;
    state.lastData = Date.now();
    $('cameraBadge').textContent = status.camera_id || '--';
    $('summary').textContent = status.summary || '已连接，等待状态摘要';
    $('scanCount').textContent = status.scan_count_total ?? '--';
    $('scanRate').textContent = status.scan_rate_per_minute == null ? '--' : Number(status.scan_rate_per_minute).toFixed(1);
    $('missDuration').textContent = status.miss_scan_duration_s == null ? '--' : `${Number(status.miss_scan_duration_s).toFixed(1)}s`;
    $('componentCount').textContent = status.active_components ?? '--';
    $('componentHint').textContent = `${status.warning_components || 0} 警告 · ${status.error_components || 0} 错误`;
    renderHealth();
  }
  function renderHealth() {
    if (state.diagnostics.length) {
      // Per-component real levels come from /api/diagnostics; VisionStatus
      // only carries aggregate counters.
      const rows = state.diagnostics
        .filter(item => state.filter === 'all' || Number(item.level) === Number(state.filter))
        .map(item => ({ name: item.name, message: item.message, level: Number(item.level) || 0 }));
      $('healthList').innerHTML = rows.map(row => `<div class="health-row"><i class="severity ${levelClass(row.level)}"></i><b>${esc(row.name)}</b><span>${esc(row.message || '运行正常')}</span></div>`).join('') || '<div class="empty">暂无组件诊断</div>';
      return;
    }
    const status = state.status;
    const names = status.components || [];
    const level = status.error_components ? 2 : status.warning_components ? 1 : 0;
    $('healthList').innerHTML = names
      .filter(([, message]) => state.filter === 'all' || level === Number(state.filter))
      .map(([name, message]) => `<div class="health-row"><i class="severity ${levelClass(level)}"></i><b>${esc(name)}</b><span>${esc(message || '运行正常')}</span></div>`)
      .join('') || '<div class="empty">暂无组件诊断</div>';
  }
  function diagnosisAdvice(item) {
    const text = `${item.name || ''} ${item.message || ''}`.toLowerCase();
    if (text.includes('camera') || text.includes('相机')) return '检查相机供电、网线和设备 User ID；确认 camera_info 正常发布。';
    if (text.includes('scanner') || text.includes('keyence')) return '检查扫码器供电、IP 地址和 TCP 端口配置。';
    if (text.includes('image')) return '检查图像编码、QoS 和相机采集状态。';
    if (text.includes('apriltag')) return '确认 Tag 位于视野内，并检查标定参数和 TF。';
    return '查看原始诊断信息并确认对应节点仍在运行。';
  }
  function renderDiagnostics(data) {
    state.diagnostics = data.statuses || [];
    const age = Number(data.header_age_s);
    $('diagMeta').textContent = `${state.diagnostics.length} 项` + (Number.isFinite(age) ? ` · ${age.toFixed(0)}s 前` : '');
    $('diagnostics').innerHTML = state.diagnostics.map(item => { const vals = Object.entries(item.values || {}).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(' · '); return `<article class="diagnostic ${levelClass(item.level)}"><div class="diagnostic-head"><b>${esc(item.name)}</b><span>${esc(levelName(item.level))}</span></div><code>${esc(item.message || '无详细信息')}</code><small>建议：${esc(diagnosisAdvice(item))}</small>${vals ? `<small>${esc(vals)}</small>` : ''}</article>`; }).join('') || '<div class="empty">暂无诊断数据</div>';
    const scanner = state.diagnostics.find(item => item.name?.endsWith(': Scanner Connection'));
    const scannerReady = Boolean(scanner) && Number(scanner.level) === 0;
    $('triggerScan').disabled = !scannerReady;
    $('triggerScan').title = scannerReady ? '' : (scanner ? (scanner.message || '扫码器离线') : '扫码器未启用');
    const camera = state.diagnostics.find(item => item.name?.endsWith(': camera_availability'));
    const image = state.diagnostics.find(item => item.name?.endsWith(': image_publish_rate'));
    $('streamText').textContent = camera && Number(camera.level) === 0 ? '相机在线' : '相机离线';
    $('feedMeta').textContent = image?.values?.fps ? `${Number(image.values.fps).toFixed(1)} FPS` : '帧率未知';
    if (camera && Number(camera.level) > 0) { $('hardwareNotice').hidden = false; $('hardwareNotice').textContent = `硬件提醒：${camera.message || '相机暂不可用'}。控制台仍可访问，设备恢复后会自动更新。`; }
    renderHealth();
  }
  function renderScans() { $('scanMeta').textContent = `${state.scans.length} 条记录`; $('scanTable').innerHTML = state.scans.slice(0, 80).map(item => `<tr><td>${formatTime(item.timestamp)}</td><td>${esc(item.source || '--')}</td><td class="data">${esc(item.data)}</td></tr>`).join('') || '<tr><td colspan="3" class="empty">暂无扫码记录</td></tr>'; }
  function renderEvents() { $('events').innerHTML = state.events.slice(0, 20).map(item => `<div class="event-row"><i class="severity ${item.event?.includes('error') ? 'error' : 'ok'}"></i><div><b>${esc(item.event || '系统事件')}</b><small>${formatTime(item.timestamp)}</small></div></div>`).join('') || '<div class="empty">暂无事件</div>'; }

  // -- hand-eye calibration wizard ----------------------------------------
  function handeyeWizardStep(data, samples, running) {
    if (running) return 3;
    if (data?.phase === 'done') return 4;
    if (samples.length >= 4) return 3;  // 手眼至少 4 组样本才允许求解
    if (samples.length || data?.session_id) return 2;  // 有会话或样本 → 进入第二步采集
    return 1;
  }
  function renderHandeyePoseGuide(samples) {
    const idx = Math.min(samples.length, HANDEYE_POSE_GUIDE.length - 1);
    if (samples.length >= HANDEYE_POSE_GUIDE.length) {
      $('handeyePoseHint').textContent = `引导姿态已完成 (${HANDEYE_POSE_GUIDE.length} 组)，可继续补充更多姿态，或直接点击"开始求解"`;
    } else {
      $('handeyePoseHint').textContent = samples.length
        ? `第 ${samples.length + 1} 组：${HANDEYE_POSE_GUIDE[idx].title} — ${HANDEYE_POSE_GUIDE[idx].hint}`
        : '点击"启动标定"后，移动机械臂到第 1 组姿态并在下方输入位姿。';
    }
  }
  function formatMatrix16(flat) {
    if (!flat || flat.length !== 16) return '--';
    const rows = [];
    for (let i = 0; i < 4; i++) {
      rows.push(flat.slice(i * 4, i * 4 + 4).map(v => Number(v).toFixed(5).padStart(9)).join('  '));
    }
    return rows.join('\n');
  }
  function renderHandeye(data) {
    state.handeye = data || {};
    const samples = data?.samples || [];
    const phase = data?.phase || 'idle';
    const running = Boolean(HANDEYE_RUNNING[phase]);
    const tagAvail = Boolean(data?.latest_tag_available);
    const targetFrame = data?.target_frame || '';
    $('handeyeTagState').textContent = tagAvail ? `标签位姿就绪 ${targetFrame ? '· ' + targetFrame : ''}` : '标签位姿未就绪';
    $('handeyeTagState').className = `status-pill ${tagAvail ? 'calibration-done' : ''}`;
    $('handeyePhase').textContent = HANDEYE_PHASES[phase] || phase;
    $('handeyePhase').className = `status-pill ${phase === 'failed' ? 'calibration-failed' : phase === 'done' ? 'calibration-done' : running ? 'calibration-starting' : ''}`;

    const step = handeyeWizardStep(data, samples, running);
    document.querySelectorAll('#handeyeWizardSteps li').forEach(li => {
      const n = Number(li.dataset.step);
      li.classList.toggle('active', n === step);
      li.classList.toggle('done', n < step);
    });
    document.querySelectorAll('#handeyeWorkspace .wizard-card').forEach(card => card.classList.toggle('locked', Number(card.dataset.step) > step));

    $('handeyeBegin').disabled = running;
    renderHandeyePoseGuide(samples);
    $('handeyeSampleCount').textContent = `${samples.length} 组`;
    $('handeyeSampleMeta').textContent = `${samples.length} 组`;

    const canCapture = tagAvail && !running;
    $('handeyeCaptureSample').disabled = !canCapture || step < 1;
    $('handeyeCaptureSample2').disabled = !canCapture || step < 2;
    $('handeyeCaptureSample2').textContent = samples.length ? `采集第 ${samples.length + 1} 组` : '采集第 1 组样本';

    const diversity = data?.diversity || {};
    const transSpan = Number(diversity.translation_span_mm || 0);
    const rotSpan = Number(diversity.rotation_span_deg || 0);
    const consec = Number(diversity.consecutive_rotation_deg || 0);
    $('diversityTrans').value = Math.min(200, transSpan); $('diversityTransValue').textContent = `${transSpan} mm`;
    $('diversityRot').value = Math.min(60, rotSpan); $('diversityRotValue').textContent = `${rotSpan}°`;
    $('diversityConsec').value = Math.min(30, consec); $('diversityConsecValue').textContent = `${consec}°`;
    const okTrans = transSpan >= 20;
    const okRot = rotSpan >= 15;
    if (!samples.length) $('diversityHint').textContent = '请采集 4 组以上位姿对';
    else if (okTrans && okRot) $('diversityHint').textContent = '姿态多样性达到推荐阈值';
    else $('diversityHint').textContent = `建议：平移跨度 ≥ 20mm（${okTrans ? '已达' : '当前 ' + transSpan + 'mm'}），旋转跨度 ≥ 15°（${okRot ? '已达' : '当前 ' + rotSpan + '°'}）`;

    $('handeyeSampleList').innerHTML = samples.map((s, i) => {
      const pose = s.robot_pose || {};
      const xyz = `(${Number(pose.x_mm || 0).toFixed(1)}, ${Number(pose.y_mm || 0).toFixed(1)}, ${Number(pose.z_mm || 0).toFixed(1)}) mm`;
      const rpy = `R ${Number(pose.roll_deg || 0).toFixed(1)}° / P ${Number(pose.pitch_deg || 0).toFixed(1)}° / Y ${Number(pose.yaw_deg || 0).toFixed(1)}°`;
      return `<article class="capture-card"><img src="/api/handeye/samples/${encodeURIComponent(s.filename)}" alt="${esc(s.filename)}"><div><b>#${i + 1} ${esc(s.filename)}</b><small>${formatTime(s.created_at)} · ${s.tag_detections ?? 0} tags</small><small class="sample-robot-pose">${xyz}</small><small class="sample-robot-pose">${rpy}</small>${s.last_robot_translation_mm ? `<small>Δ ${s.last_robot_translation_mm}mm / ${s.last_robot_rotation_deg}°</small>` : ''}</div><button class="capture-delete" data-handeye-delete="${esc(s.filename)}" title="删除样本" aria-label="删除样本">×</button></article>`;
    }).join('') || '<div class="empty">尚未采集手眼样本</div>';
    document.querySelectorAll('[data-handeye-delete]').forEach(button => button.onclick = async () => {
      await fetch(`/api/handeye/samples/${encodeURIComponent(button.dataset.handeyeDelete)}`, { method: 'DELETE' });
      loadHandeye();
    });

    $('handeyeStart').disabled = running || samples.length < 4;
    $('handeyeStart').title = samples.length < 4 ? `至少需要 4 组样本（当前 ${samples.length} 组）` : '';
    $('handeyeProgress').textContent = `${samples.length} 组样本`;
    $('handeyeProgressBar').max = Math.max(samples.length, 1);
    $('handeyeProgressBar').value = phase === 'done' ? samples.length : (running ? Math.ceil(samples.length / 2) : samples.length);

    const result = data?.result;
    $('handeyeResult').hidden = !result;
    $('handeyeApply').disabled = !result;
    $('handeyeApplyHint').textContent = result ? '确认结果后点击"应用手眼"写入配置 YAML，并尝试热重载静态 TF 广播器。' : '求解完成后可将手眼标定矩阵写入配置路径。';
    if (result) {
      $('handeyeMeanTrans').textContent = Number(result.mean_translation_error_mm).toFixed(2);
      $('handeyeMaxTransR').textContent = Number(result.max_translation_error_mm).toFixed(2);
      $('handeyeMeanRot').textContent = Number(result.mean_rotation_error_deg).toFixed(3);
      $('handeyeMaxRotR').textContent = Number(result.max_rotation_error_deg).toFixed(3);
      $('handeyeResultMeta').textContent = `${result.created_at} · ${result.algorithm_used}`;
      const t = result.translation_xyz_mm || [];
      $('handeyeC2GTrans').textContent = t.length === 3 ? `X=${t[0].toFixed(2)} mm  Y=${t[1].toFixed(2)} mm  Z=${t[2].toFixed(2)} mm` : '--';
      $('handeyeAlgoSamples').textContent = `${result.algorithm_used}  ·  ${result.samples_used} 组`;
      $('handeyeG2CMatrix').textContent = formatMatrix16(result.gripper_to_camera_matrix);
      $('handeyeDownload').href = `/api/handeye/history/${encodeURIComponent(result.yaml_filename)}`;
    }
    $('handeyeHistory').innerHTML = (data?.history || []).map(item => {
      const t = item.translation_xyz_mm || [0, 0, 0];
      const transStr = t.length === 3 ? `t=(${t[0].toFixed(1)},${t[1].toFixed(1)},${t[2].toFixed(1)})mm` : '';
      return `<article class="history-row"><div><b>${esc(item.id)}</b><small>${esc(item.created_at)} · ${esc(item.algorithm_used || '--')} · ${item.samples_used || 0} 组 · err ${Number(item.mean_translation_error_mm || 0).toFixed(2)}mm / ${Number(item.mean_rotation_error_deg || 0).toFixed(3)}° ${transStr}</small></div><div class="toolbar"><a class="button" href="/api/handeye/history/${encodeURIComponent(item.yaml_filename)}" download>YAML</a><button class="button" data-handeye-apply="${esc(item.id)}">应用</button></div></article>`;
    }).join('') || '<div class="empty">暂无历史手眼标定记录</div>';
    document.querySelectorAll('[data-handeye-apply]').forEach(button => button.onclick = () => applyHandeye(button.dataset.handeyeApply));

    const defaultHint = { 1: '配置好参数后点击"启动标定"', 2: tagAvail ? '输入当前机械臂位姿后点击"采集样本"' : '等待 AprilTag 位姿数据就绪（检查流水线）', 3: '点击"开始求解"计算手眼矩阵', 4: '求解完成，可应用结果' }[step];
    $('handeyeMessage').textContent = data?.message || defaultHint;
  }
  async function loadHandeye() { try { renderHandeye(await get('/api/handeye')); $('handeyeImage').src = handeyeImageUrl(); } catch {} }
  async function handeyeAction(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw Error(data.error || '手眼操作失败'); renderHandeye(data); return data; }
  async function applyHandeye(id) {
    const output = $('handeyeApplyResult');
    output.className = 'result'; output.textContent = '正在应用手眼标定结果...';
    try {
      const response = await fetch('/api/handeye/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || '应用手眼失败');
      output.textContent = data.message || '手眼已应用';
      output.className = 'result ok';
    } catch (error) { output.textContent = error.message; output.className = 'result bad'; }
  }

  // -- calibration wizard -------------------------------------------------
  function wizardStep(data, captures, running) {
    if (running) return 3;
    if (data?.phase === 'done') return 4;
    if (captures.length >= 3) return 3;  // 采集满足最小数量，允许点击第三步"一键标定"
    if (captures.length || data?.session_id) return 2;  // 有会话或图像 → 进入第二步采集
    return 1;
  }
  function renderPoseGuide(captures) {
    const idx = Math.min(captures.length, POSE_GUIDE.length - 1);
    $('poseGuide').innerHTML = POSE_GUIDE.map((pose, i) => `<li class="${i < captures.length ? 'done' : i === idx ? 'current' : ''}"><b>${esc(pose.title)}</b><span>${esc(pose.hint)}</span></li>`).join('');
    if (captures.length >= POSE_GUIDE.length) {
      $('poseHint').textContent = '引导视角已完成，可继续补拍或直接一键标定';
    } else {
      $('poseHint').textContent = captures.length
        ? `当前任务：${POSE_GUIDE[idx].title} — ${POSE_GUIDE[idx].hint}`
        : '等待启动标定';
    }
    $('calibrationCapture').textContent = captures.length >= POSE_GUIDE.length ? '补拍一张' : `拍照：${POSE_GUIDE[idx].title}`;
  }
  function renderCalibration(data) {
    state.calibration = data || {};
    const captures = data?.captures || [];
    const phase = data?.phase || 'idle';
    const running = RUNNING_PHASES.includes(phase);
    const service = data?.service || {};
    const serviceStatus = service.status || 'stopped';
    const serviceLabel = { stopped: '标定服务未运行', starting: '标定服务启动中', ready: '标定服务运行中', external: '标定服务由外部进程运行' };
    $('calibrationServiceState').textContent = serviceLabel[serviceStatus] || '标定服务状态未知';
    $('calibrationServiceState').className = `status-pill ${serviceStatus === 'ready' ? 'calibration-done' : serviceStatus === 'starting' ? 'calibration-starting' : serviceStatus === 'external' ? 'calibration-external' : ''}`;
    $('calibrationPhase').textContent = CALIB_PHASES[phase] || phase;
    $('calibrationPhase').className = `status-pill ${phase === 'failed' ? 'calibration-failed' : phase === 'done' ? 'calibration-done' : ''}`;

    const canStopService = service.managed && (serviceStatus === 'ready' || serviceStatus === 'starting');
    $('calibrationStopService').hidden = !canStopService;

    const step = wizardStep(data, captures, running);
    document.querySelectorAll('#wizardSteps li').forEach(li => {
      const n = Number(li.dataset.step);
      li.classList.toggle('active', n === step);
      li.classList.toggle('done', n < step);
    });
    document.querySelectorAll('.wizard-card').forEach(card => card.classList.toggle('locked', Number(card.dataset.step) > step));

    const detectedCount = captures.filter(item => Number(item.detections) > 0).length;
    $('calibrationBegin').disabled = running || serviceStatus === 'starting';
    $('calibrationBegin').textContent = service.available ? '启动标定（新建采集会话）' : '启动标定服务';
    renderPoseGuide(captures);
    $('captureCount').textContent = `${captures.length} 张`;
    $('captureMeta').textContent = `${captures.length} 张 · ${detectedCount} 张有效`;
    $('calibrationCapture').disabled = running;
    const coverage = data?.coverage || {};
    [['X', coverage.x || 0], ['Y', coverage.y || 0], ['Size', coverage.size || 0], ['Skew', coverage.skew || 0]].forEach(([axis, value]) => { $(`coverage${axis}`).value = value; $(`coverage${axis}Value`).textContent = `${value}%`; });
    $('coverageHint').textContent = detectedCount < 8 ? '按提示逐步拍摄，覆盖边缘、远近与倾角' : '覆盖度达到建议采集量';
    $('captureList').innerHTML = captures.map(item => `<article class="capture-card"><img src="/api/calibration/captures/${encodeURIComponent(item.filename)}" alt="${esc(item.filename)}"><div><b>${esc(item.filename)}</b><small>${formatTime(item.created_at)} · ${item.detections ?? 0} tags</small></div><button class="capture-delete" data-capture-delete="${esc(item.filename)}" title="删除图像" aria-label="删除图像">×</button></article>`).join('') || '<div class="empty">尚未拍摄标定图像</div>';
    document.querySelectorAll('[data-capture-delete]').forEach(button => button.onclick = async () => { await fetch(`/api/calibration/captures/${encodeURIComponent(button.dataset.captureDelete)}`, { method: 'DELETE' }); loadCalibration(); });

    $('calibrationStart').disabled = running || captures.length < 3;
    if (captures.length < 3) {
      $('calibrationStart').title = `至少需要 3 张标定图像（当前 ${captures.length} 张）`;
    } else if (detectedCount < captures.length) {
      $('calibrationStart').title = `已采集 ${captures.length} 张；其中 ${detectedCount} 张检测到标签（仅作可视化参考，不影响后端标定）`;
    } else {
      $('calibrationStart').title = '';
    }
    const processed = Number(data?.images_processed || 0);
    $('calibrationProgress').textContent = `${processed} / ${Math.max(captures.length, 1)}`;
    $('calibrationProgressBar').max = Math.max(captures.length, 1);
    $('calibrationProgressBar').value = phase === 'done' ? captures.length : processed;
    $('calibrationCancel').disabled = !running;

    const result = data?.result;
    $('calibrationResult').hidden = !result;
    $('calibrationApply').disabled = !result;
    $('applyHint').textContent = result
      ? '确认结果后点击"应用内参"写入相机配置；重启流水线容器后生效。'
      : '标定完成后可将内参写入相机配置文件，重启流水线容器后生效。';
    if (result) {
      $('resultError').textContent = Number(result.reprojection_error).toFixed(3);
      $('resultImages').textContent = result.images_used;
      $('resultMeta').textContent = `${result.image_width} x ${result.image_height} · ${result.created_at}`;
      const K = result.camera_matrix || [];
      $('resultMatrix').textContent = K.length === 9 ? `${K.slice(0,3).map(v=>Number(v).toFixed(2)).join('  ')}\n${K.slice(3,6).map(v=>Number(v).toFixed(2)).join('  ')}\n${K.slice(6,9).map(v=>Number(v).toFixed(2)).join('  ')}` : '--';
      $('resultDistortion').textContent = (result.distortion_coefficients || []).map(v => Number(v).toFixed(5)).join('  ');
      $('calibrationDownload').href = `/api/calibration/history/${encodeURIComponent(result.yaml_filename)}`;
      const last = captures[captures.length - 1];
      if (last) $('resultOriginal').src = `/api/calibration/captures/${encodeURIComponent(last.filename)}`;
      $('resultUndistorted').src = result.undistorted_filename ? `/api/calibration/history/${encodeURIComponent(result.undistorted_filename)}` : '';
    }
    $('calibrationHistory').innerHTML = (data?.history || []).map(item => `<article class="history-row"><div><b>${esc(item.id)}</b><small>${esc(item.created_at)} · RMS ${Number(item.reprojection_error).toFixed(3)} px · ${item.images_used} 张</small></div><div class="toolbar"><a class="button" href="/api/calibration/history/${encodeURIComponent(item.yaml_filename)}" download>YAML</a><button class="button" data-apply="${esc(item.id)}">应用</button></div></article>`).join('') || '<div class="empty">暂无历史标定记录</div>';
    document.querySelectorAll('[data-apply]').forEach(button => button.onclick = () => applyCalibration(button.dataset.apply));

    const defaultHint = { 1: '点击"启动标定"开始', 2: '按提示逐步拍照', 3: '点击"一键标定"计算内参', 4: '标定完成，可应用内参' }[step];
    $('calibrationMessage').textContent = data?.message || defaultHint;
  }
  async function loadCalibration() { try { renderCalibration(await get('/api/calibration')); $('calibrationImage').src = calibrationImageUrl(); } catch {} }
  async function calibrationAction(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw Error(data.error || '标定操作失败'); renderCalibration(data); }
  async function applyCalibration(id) {
    const output = $('applyResult');
    output.className = 'result'; output.textContent = '正在应用内参...';
    try {
      const response = await fetch('/api/calibration/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || '应用内参失败');
      output.textContent = data.message || '内参已应用';
      output.className = 'result ok';
    } catch (error) { output.textContent = error.message; output.className = 'result bad'; }
  }
  async function loadDiagnostics() { try { renderDiagnostics(await get('/api/diagnostics')); } catch {} }
  async function load() { try { const [aggregate, scans, events] = await Promise.all([get('/api/aggregate'), get('/api/scans?limit=80'), get('/api/events?limit=20')]); renderStatus(Object.values(aggregate.cameras || {})[0]); state.scans = scans.reverse(); state.events = events.reverse(); renderScans(); renderEvents(); setConnection(true); await loadDiagnostics(); } catch { setConnection(false); $('summary').textContent = '无法连接 Dashboard API，请检查 ROS 2 节点或容器状态'; } }
  async function action(url, label) { const result = $('controlResult'); result.className = 'result'; result.textContent = `${label}中...`; try { const response = await fetch(url, { method: 'POST' }); const data = await response.json(); if (!response.ok || data.success === false) throw Error(data.message || `${label}失败`); result.textContent = `${label}成功`; result.className = 'result ok'; } catch (error) { result.textContent = error.message || `${label}失败`; result.className = 'result bad'; } }
  function connectWs() { const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'; const ws = new WebSocket(`${protocol}//${location.host}/ws`); ws.onopen = () => setConnection(true); ws.onclose = () => { setConnection(false); setTimeout(connectWs, 3000); }; ws.onmessage = event => { try { const message = JSON.parse(event.data); if (message.v !== undefined && message.v !== 1) return; if (message.type === 'status') renderStatus(message.data); if (message.type === 'scan') { state.scans = [message.data, ...state.scans].slice(0, 200); renderScans(); } } catch {} }; }

  $('refreshButton').onclick = load;
  $('feedImage').onerror = () => {
    if (!$('feedImage').getAttribute('src')) return;
    $('feedImage').removeAttribute('src');
    $('feedImage').hidden = true;
    $('feedEmpty').hidden = false;
    if (state.live) { state.live = false; $('liveButton').textContent = '启动实时流'; }
  };
  $('snapshotButton').onclick = () => { $('feedImage').src = snapshotUrl(); $('feedImage').hidden = false; $('feedEmpty').hidden = true; };
  $('liveButton').onclick = () => { state.live = !state.live; $('liveButton').textContent = state.live ? '停止实时流' : '启动实时流'; $('feedImage').src = state.live ? streamUrl() : ''; $('feedImage').hidden = !state.live; $('feedEmpty').hidden = state.live; };
  $('applyExposure').onclick = () => action(`/api/set_exposure?value=${encodeURIComponent($('exposure').value)}`, '曝光应用');
  $('applyGain').onclick = () => action(`/api/set_gain?value=${encodeURIComponent($('gain').value)}`, '增益应用');
  $('applyImage').onclick = async () => { await action(`/api/set_gamma?value=${encodeURIComponent($('gamma').value)}`, 'Gamma 应用'); await action(`/api/set_brightness?value=${encodeURIComponent($('brightness').value)}`, '亮度应用'); await action(`/api/set_binning?x=${encodeURIComponent($('binningX').value)}&y=${encodeURIComponent($('binningY').value)}`, 'Binning 应用'); };
  $('triggerScan').onclick = () => { if (confirm('确认触发实体扫码枪？')) action('/api/trigger_scan', '扫码触发'); };
  $('eventsButton').onclick = async () => { try { state.events = (await get('/api/events?limit=20')).reverse(); renderEvents(); } catch {} };
  $('calibrationBegin').onclick = async () => {
    try {
      const service = state.calibration?.service || {};
      if (!service.available) {
        await fetch('/api/calibration/service/toggle', { method: 'POST' });
        $('calibrationMessage').textContent = '标定服务启动中，就绪后（状态变为"运行中"）再次点击"启动标定"';
        return;
      }
      await calibrationAction('/api/calibration/session', { method: 'POST' });
      $('calibrationMessage').textContent = '采集会话已创建，请按提示逐步拍照';
    } catch (error) { $('calibrationMessage').textContent = error.message; }
  };
  $('calibrationNewSession').onclick = async () => { try { await calibrationAction('/api/calibration/session', { method: 'POST' }); $('calibrationMessage').textContent = '已新建采集会话，请按提示逐步拍照'; } catch (error) { $('calibrationMessage').textContent = error.message; } };
  $('calibrationCapture').onclick = async () => { try { await calibrationAction('/api/calibration/captures', { method: 'POST' }); } catch (error) { $('calibrationMessage').textContent = error.message; } };
  $('calibrationStart').onclick = async () => { const payload = { rows:+$('calibRows').value, cols:+$('calibCols').value, tag_size_m:+$('calibTagSize').value, tag_spacing_m:+$('calibTagSpacing').value, tag_family:$('calibTagFamily').value, max_reprojection_error:+$('calibMaxError').value, timeout_s:+$('calibTimeout').value }; try { await calibrationAction('/api/calibration/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); } catch (error) { $('calibrationMessage').textContent = error.message; } };
  $('calibrationCancel').onclick = async () => { try { await calibrationAction('/api/calibration/cancel', { method: 'POST' }); } catch (error) { $('calibrationMessage').textContent = error.message; } };
  $('calibrationStopService').onclick = async () => { try { await fetch('/api/calibration/service/toggle', { method: 'POST' }); await loadCalibration(); $('calibrationMessage').textContent = '标定服务已停止'; } catch (error) { $('calibrationMessage').textContent = error.message; } };
  $('calibrationApply').onclick = () => { const result = state.calibration?.result; if (result) applyCalibration(result.id); };

  // -- hand-eye calibration UI handlers ------------------------------
  $('handeyeBegin').onclick = async () => {
    try { await handeyeAction('/api/handeye/session', { method: 'POST' }); $('handeyeMessage').textContent = '采集会话已创建。移动机械臂到第 1 组姿态，输入位姿后点击"采集样本"。'; }
    catch (error) { $('handeyeMessage').textContent = error.message; }
  };
  $('handeyeNewSession').onclick = async () => {
    try { await handeyeAction('/api/handeye/session', { method: 'POST' }); $('handeyeMessage').textContent = '已新建手眼采集会话，请从第 1 组姿态重新采集。'; }
    catch (error) { $('handeyeMessage').textContent = error.message; }
  };
  async function doHandeyeCapture() {
    const payload = {
      x_mm: Number($('poseXmm').value), y_mm: Number($('poseYmm').value), z_mm: Number($('poseZmm').value),
      roll_deg: Number($('poseRoll').value), pitch_deg: Number($('posePitch').value), yaw_deg: Number($('poseYaw').value),
    };
    try {
      await handeyeAction('/api/handeye/samples', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      $('handeyeMessage').textContent = `已采集第 ${(state.handeye?.samples?.length || 0)} 组样本。移动机械臂到下一组姿态，再次点击"采集样本"。`;
    } catch (error) { $('handeyeMessage').textContent = error.message; }
  }
  $('handeyeCaptureSample').onclick = doHandeyeCapture;
  $('handeyeCaptureSample2').onclick = doHandeyeCapture;
  $('handeyePastePose').onclick = () => {
    const samples = state.handeye?.samples || [];
    if (!samples.length) { $('handeyeMessage').textContent = '尚无已采集的样本位姿可填入'; return; }
    const p = samples[samples.length - 1].robot_pose || {};
    $('poseXmm').value = p.x_mm ?? 0; $('poseYmm').value = p.y_mm ?? 0; $('poseZmm').value = p.z_mm ?? 0;
    $('poseRoll').value = p.roll_deg ?? 0; $('posePitch').value = p.pitch_deg ?? 0; $('poseYaw').value = p.yaw_deg ?? 0;
    $('handeyeMessage').textContent = '已填入上一组的机械臂位姿，请根据当前实际姿态进行微调整';
  };
  $('handeyeStart').onclick = async () => {
    const payload = {
      algorithm: $('handeyeAlgo').value,
      base_frame: $('handeyeBaseFrame').value.trim() || 'base_link',
      gripper_frame: $('handeyeGripperFrame').value.trim() || 'tool0',
      camera_frame: $('handeyeCameraFrame').value.trim() || 'camera_optical_frame',
      target_frame: $('handeyeTargetFrame').value.trim() || 'apriltag_board',
      max_closed_loop_translation_m: Number($('handeyeMaxTrans').value) / 1000.0,
      max_closed_loop_rotation_deg: Number($('handeyeMaxRot').value),
    };
    try { await handeyeAction('/api/handeye/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); }
    catch (error) { $('handeyeMessage').textContent = error.message; }
  };
  $('handeyeApply').onclick = () => { const result = state.handeye?.result; if (result) applyHandeye(result.id); };

  document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => { document.querySelectorAll('[data-filter]').forEach(item => item.classList.remove('active')); button.classList.add('active'); state.filter = button.dataset.filter; renderHealth(); });
  $('themeButton').onclick = () => { const light = document.documentElement.dataset.theme === 'light'; document.documentElement.dataset.theme = light ? 'dark' : 'light'; };
  document.addEventListener('keydown', event => { if (event.target instanceof Element && event.target.matches('input,select,textarea')) return; if (event.key.toLowerCase() === 'r') load(); if (event.shiftKey && event.key.toLowerCase() === 's') $('liveButton').click(); if (event.shiftKey && event.key.toLowerCase() === 't') $('triggerScan').click(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  setInterval(() => {
    $('clock').textContent = new Date().toLocaleTimeString('zh-CN', { hour12:false });
    if (state.wsOnline) {
      const stale = state.lastData && Date.now() - state.lastData > 10000;
      $('connectionDot').className = stale ? 'warn' : 'ok';
      $('connectionText').textContent = stale ? '数据陈旧' : '数据在线';
    }
  }, 1000);
  setInterval(() => { if (!document.hidden && !state.wsOnline) load(); }, 15000);
  setInterval(() => { if (!document.hidden) loadDiagnostics(); }, 5000);
  setInterval(() => { if (!document.hidden) loadCalibration(); }, 1000);
  setInterval(() => { if (!document.hidden) loadHandeye(); }, 1000);
  load(); loadCalibration(); loadHandeye(); connectWs();
})();
