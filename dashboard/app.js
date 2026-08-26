const kpisRoot = document.getElementById('kpis');
const scoreChart = document.getElementById('scoreChart');
const scoreDefinition = document.getElementById('scoreDefinition');
const recordsTable = document.getElementById('recordsTable');
const weaknessList = document.getElementById('weaknessList');
const statusCard = document.getElementById('statusCard');
const riskSummary = document.getElementById('riskSummary');
const searchInput = document.getElementById('searchInput');
const refreshBtn = document.getElementById('refreshBtn');
const lastUpdated = document.getElementById('lastUpdated');
let selectedUrl = null;

const navButtons = document.querySelectorAll('.nav-item');
navButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    navButtons.forEach((b) => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.panel').forEach((panel) => {
      panel.classList.toggle('active', panel.id === btn.dataset.panel);
    });
  });
});

function statusClass(status) {
  if (status === 'good') return 'status-good';
  if (status === 'needs_attention') return 'status-needs_attention';
  return 'status-critical';
}

function badgeClass(score) {
  if (score > 0) return 'success';
  if (score === 0) return 'warning';
  return 'danger';
}

async function loadSummary() {
  try {
    const res = await fetch('/api/summary', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderSummary(data);
    const stamp = new Date().toLocaleString('es-ES');
    lastUpdated.textContent = `Última actualización: ${stamp}`;
  } catch (error) {
    lastUpdated.textContent = 'No se pudieron cargar los resultados nuevos';
    console.error('Error cargando resumen:', error);
  }
}

function formatScore(score) {
  return Number(score).toFixed(1);
}

function renderSummary(data) {
  const cards = [
    { label: 'Registros', value: data.total_records },
    { label: 'Exitosos', value: data.positive_cases },
    { label: 'Tasa éxito', value: `${(data.success_rate * 100).toFixed(1)}%` },
    { label: 'Delta base', value: data.baseline_delta }
  ];

  kpisRoot.innerHTML = cards.map((item) => `
    <div class="kpi-card">
      <div class="kpi-label">${item.label}</div>
      <div class="kpi-value">${item.value}</div>
    </div>
  `).join('');

  scoreChart.innerHTML = Object.entries(data.score_distribution || {}).map(([score, count]) => {
    const pct = (count / data.total_records) * 100 || 0;
    return `
      <div class="chart-row">
        <span>${score}</span>
        <div class="chart-bar" style="width:${pct}%"></div>
        <strong>${count}</strong>
      </div>
    `;
  }).join('');

  const rubric = data.score_definition || {};
  scoreDefinition.innerHTML = `
    <details class="score-explainer" open>
      <summary>Cómo se asigna el score</summary>
      <div class="score-definition-body">
        <div><strong>0.0</strong>: ${rubric['0.0'] || 'Sin evidencia útil.'}</div>
        <div><strong>1.0</strong>: ${rubric['1.0'] || 'Sitio accesible, pero aún no hay documento fuerte.'}</div>
        <div><strong>2.0</strong>: ${rubric['2.0'] || 'Se detectó un candidato, pero sin fuerte evidencia operativa.'}</div>
        <div><strong>3.0</strong>: ${rubric['3.0'] || 'Documento relevante con contexto y fecha detectable.'}</div>
        <div><strong>4.0</strong>: ${rubric['4.0'] || 'Alta confianza, acceso y validación suficiente.'}</div>
      </div>
    </details>
    <details class="score-explainer">
      <summary>Regla operativa de defensa del score</summary>
      <div class="score-definition-body">
        <p>El score final no se evalúa solo por la apariencia de la URL. Se exige evidencia operativa: acceso real, redirecciones observadas, presencia de enlaces documentales relevantes, palabras clave de subpáginas, y ausencia de bloqueo por robots o fallas de conexión.</p>
        <ul>
          <li>Si hay <strong>CONN_ERROR, DNS_ERROR, SSL_ERROR, TIMEOUT</strong> o bloqueo por robots, el score no puede sostener un valor por encima de <strong>2.0</strong>.</li>
          <li>Si hay un candidato claro con contexto documental y acceso real, el valor puede llegar a <strong>3.0</strong>.</li>
          <li>Solo si hay acceso, documento relevante y metadata útil se puede llegar a <strong>4.0</strong>.</li>
        </ul>
      </div>
    </details>
  `;

  const statusText = {
    good: 'Buen rendimiento',
    needs_attention: 'Requiere atención',
    critical: 'Crítico'
  }[data.status] || 'Sin estado';

  statusCard.className = `status-pill ${statusClass(data.status)}`;
  statusCard.textContent = statusText;

  weaknessList.innerHTML = (data.weaknesses && data.weaknesses.length ? data.weaknesses : ['Sin debilidades dominantes']).map((w) => `<li>${w}</li>`).join('');

  const risks = [
    `Tasa de éxito: ${(data.success_rate * 100).toFixed(1)}%`,
    `Total de registros evaluados: ${data.total_records}`,
    `La mayor debilidad observada es: ${data.weaknesses?.[0] || 'Sin debilidad dominante'}`
  ];
  riskSummary.innerHTML = risks.map((risk) => `<div class="risk-item">${risk}</div>`).join('');

  renderRecords(data.records || []);
}

function renderRecords(records) {
  const term = (searchInput.value || '').toLowerCase();
  const filtered = records.filter((row) => {
    const haystack = `${row.Fuente || ''} ${row.Url_Original || ''} ${row.Institucion || ''}`.toLowerCase();
    return haystack.includes(term);
  });

  recordsTable.innerHTML = filtered.map((row) => {
    const score = Number(row.Score_Excel || 0);
    const label = score > 0 ? 'Éxito' : 'Revisión';
    const badge = score > 0 ? 'success' : 'warning';
    const rowUrl = row.Url_Original || row.url || '';
    const isSelected = selectedUrl && rowUrl === selectedUrl;

    return `
      <tr data-url="${rowUrl.replace(/"/g, '&quot;')}" class="${isSelected ? 'row-selected' : ''}" style="cursor:pointer;">
        <td>${row.Fuente || '-'}</td>
        <td><a href="${rowUrl || '#'}" target="_blank" rel="noreferrer">${rowUrl || '-'}</a></td>
        <td>${formatScore(score)}</td>
        <td>${row.HTTP_Status || '-'}</td>
        <td><span class="badge ${badge}">${label}</span></td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="5">No se encontraron registros.</td></tr>';

  recordsTable.querySelectorAll('tr[data-url]').forEach((rowEl) => {
    rowEl.addEventListener('click', () => {
      const url = rowEl.getAttribute('data-url');
      selectedUrl = url || null;
      const selected = records.find((item) => {
        const candidate = item.Url_Original || item.url || '';
        return candidate === url;
      });
      showRecordEvidence(selected || null);
    });
  });

  const activeRecord = filtered.find((row) => {
    const candidate = row.Url_Original || row.url || '';
    return selectedUrl && candidate === selectedUrl;
  }) || filtered[0] || null;

  if (activeRecord) {
    selectedUrl = activeRecord.Url_Original || activeRecord.url || selectedUrl;
    showRecordEvidence(activeRecord);
  } else {
    selectedUrl = null;
    showRecordEvidence(null);
  }
}

function buildScoreReason(record, rawScore, effectiveScore) {
  const diagnostics = Array.isArray(record.Diagnosticos_Excel) ? record.Diagnosticos_Excel : [];
  const reasons = [];

  if (rawScore > effectiveScore) {
    reasons.push(`El score bruto era ${rawScore.toFixed(1)}, pero se redujo porque no hubo acceso operativo verificable.`);
  } else if (rawScore >= 3.0) {
    reasons.push(`El score bruto de ${rawScore.toFixed(1)} refleja señales positivas, pero estas solo se sostienen si hay acceso real a la fuente.`);
  }

  if (record.Doc_Links_Found_In_Seed && Number(record.Doc_Links_Found_In_Seed) > 0) {
    reasons.push(`Se detectaron ${record.Doc_Links_Found_In_Seed} enlaces documentales en la semilla de la fuente.`);
  } else {
    reasons.push('No se observaron enlaces documentales claros en la semilla analizada.');
  }

  if (record.Subpage_Keywords_Found && Number(record.Subpage_Keywords_Found) > 0) {
    reasons.push(`Se detectaron ${record.Subpage_Keywords_Found} señales temáticas relevantes en subpáginas.`);
  } else {
    reasons.push('No se identificaron palabras clave relevantes en subpáginas asociadas.');
  }

  if (record.HTTP_Status) {
    reasons.push(`El acceso respondió con HTTP ${record.HTTP_Status}.`);
  }

  if (record.Robots_Allowed !== undefined) {
    reasons.push(`robots.txt: ${record.Robots_Allowed ? 'permitido' : 'bloqueado'}.`);
  }

  if (record.Error_Detail) {
    reasons.push(`Error operativo observado: ${record.Error_Detail}.`);
  }

  if (diagnostics.length) {
    reasons.push(`Diagnósticos relevantes: ${diagnostics.join('; ')}.`);
  }

  if (effectiveScore < rawScore) {
    reasons.push('Se aplicó un límite defensible: una URL con bloqueo real, DNS/SSL o CONN_ERROR no puede sostener un score superior a 2.0.');
  }

  if (effectiveScore >= 3.0) {
    reasons.push('La suma de señales documentales y acceso viable respalda un score medio-alto.');
  }

  return reasons;
}

function buildEvidenceLists(record) {
  const diagnostics = Array.isArray(record.Diagnosticos_Excel) ? record.Diagnosticos_Excel : [];
  const observed = [];
  const operational = [];

  if (record.Doc_Links_Found_In_Seed && Number(record.Doc_Links_Found_In_Seed) > 0) {
    observed.push(`Se detectaron ${record.Doc_Links_Found_In_Seed} enlaces documentales en la semilla.`);
  } else {
    observed.push('No se observaron enlaces documentales claros en la semilla analizada.');
  }

  if (record.Subpage_Keywords_Found && Number(record.Subpage_Keywords_Found) > 0) {
    observed.push(`Se detectaron ${record.Subpage_Keywords_Found} señales temáticas relevantes en subpáginas.`);
  } else {
    observed.push('No se identificaron palabras clave relevantes en subpáginas asociadas.');
  }

  if (diagnostics.length) {
    observed.push(`Diagnósticos recuperados: ${diagnostics.join('; ')}.`);
  }

  if (record.HTTP_Status) {
    operational.push(`HTTP status observado: ${record.HTTP_Status}.`);
  }

  if (record.Robots_Allowed !== undefined) {
    operational.push(`robots.txt: ${record.Robots_Allowed}.`);
  }

  if (record.Error_Detail) {
    operational.push(`Error operativo: ${record.Error_Detail}.`);
  }

  if (record.Final_Url && record.Url_Original && record.Final_Url !== record.Url_Original) {
    operational.push(`La URL final redireccionó a: ${record.Final_Url}.`);
  }

  return { observed, operational };
}

function showRecordEvidence(record) {
  const panel = document.getElementById('recordDetailContent');
  const detailHost = document.getElementById('recordDetail');
  if (!record) {
    panel.innerHTML = 'Seleccione una fila para ver el respaldo del score.';
    return;
  }

  detailHost.style.transform = 'translateY(4px)';
  detailHost.style.opacity = '0.7';

  setTimeout(() => {
    detailHost.style.transform = 'translateY(0)';
    detailHost.style.opacity = '1';
  }, 150);

  // Normalize evidence coming from different export shapes:
  // - record.evidence (server-side enrichment)
  // - record.Document_Evidence (exported by rebuild script)
  // - record.document_evidence (alternate key)
  const evidenceFromRecord = record.evidence || {};
  const legacyDocEvidence = record.Document_Evidence || record.document_evidence || evidenceFromRecord.document_evidence || {};
  const evidenceSignals = (evidenceFromRecord.signals || record.signals || []);

  const rawScore = Number(record.Score_Excel || 0);
  const effectiveScore = Number(evidenceFromRecord.score || legacyDocEvidence.quality_score || 0);
  const documentEvidence = legacyDocEvidence || { keyword_hits: [], snippet_text: '', quality_score: 0, file_type: null };
  const capped = rawScore > effectiveScore && effectiveScore <= 2.0;
  const diagnostics = Array.isArray(record.Diagnosticos_Excel) ? record.Diagnosticos_Excel : [];
  const scoreReasons = buildScoreReason(record, rawScore, effectiveScore);
  const evidenceLists = buildEvidenceLists(record);

  const defendabilityText = capped
    ? 'Score limitado por acceso operativo: la URL no es recuperable o presenta bloqueo real (DNS/SSL/robots/CONN_ERROR), por lo que no puede sostener un score 4.0.'
    : 'Score defendible: la URL presenta señales observadas de contenido y acceso suficientes para sostener la puntuación final.';

  panel.innerHTML = `
    <div class="detail-grid">
      <div class="detail-box">
        <strong>Fuente</strong>
        ${record.Fuente || '-'}
      </div>
      <div class="detail-box">
        <strong>Institución</strong>
        ${record.Institucion || '-'}
      </div>
      <div class="detail-box">
        <strong>Score bruto</strong>
        ${rawScore.toFixed(1)}
      </div>
      <div class="detail-box">
        <strong>Score defendible</strong>
        ${effectiveScore.toFixed(1)}
      </div>
      <div class="detail-box">
        <strong>HTTP</strong>
        ${record.HTTP_Status || '-'}
      </div>
      <div class="detail-box">
        <strong>Robots</strong>
        ${record.Robots_Allowed !== undefined ? String(record.Robots_Allowed) : '-'}
      </div>
      <div class="detail-box detail-box-wide">
        <strong>URL original</strong>
        <a href="${record.Url_Original || '#'}" target="_blank" rel="noreferrer">${record.Url_Original || '-'}</a>
      </div>
      <div class="detail-box detail-box-wide">
        <strong>URL final</strong>
        ${record.Final_Url || '-'}
      </div>
    </div>

    <div class="detail-box">
      <strong>Estado del score</strong>
      <div>${defendabilityText}</div>
    </div>

    <div class="detail-box">
      <strong>Cómo se asignó esta puntuación</strong>
      <ul class="evidence-list">
        ${scoreReasons.map((reason) => `<li>${reason}</li>`).join('')}
      </ul>
    </div>

    <div class="detail-box">
      <strong>Evidencia observada</strong>
      <div class="metric-grid">
        <div class="metric-item"><span>Enlaces documentales detectados</span><strong>${record.Doc_Links_Found_In_Seed ?? 0}</strong></div>
        <div class="metric-item"><span>Palabras clave relevantes</span><strong>${record.Subpage_Keywords_Found ?? 0}</strong></div>
        <div class="metric-item"><span>Diagnósticos</span><strong>${diagnostics.length}</strong></div>
      </div>
      <ul class="evidence-list">
        ${evidenceLists.observed.map((item) => `<li>${item}</li>`).join('')}
      </ul>
    </div>

    <div class="detail-box">
      <strong>Evidencia operativa</strong>
      <ul class="evidence-list">
        ${evidenceLists.operational.map((item) => `<li>${item}</li>`).join('') || '<li>No hay evidencia operativa adicional.</li>'}
      </ul>
    </div>

    <div class="detail-box">
      <strong>Evidencia documental encontrada</strong>
      <div class="metric-grid">
        <div class="metric-item"><span>Tipo de archivo</span><strong>${documentEvidence.file_type || '-'}</strong></div>
        <div class="metric-item"><span>Calidad documental</span><strong>${Number(documentEvidence.quality_score || 0).toFixed(1)}</strong></div>
        <div class="metric-item"><span>Palabras clave</span><strong>${(documentEvidence.keyword_hits || []).length}</strong></div>
      </div>
      <ul class="evidence-list">
        ${(documentEvidence.keyword_hits || []).length ? documentEvidence.keyword_hits.map((hit) => `<li>Palabra clave documental: ${hit}</li>`).join('') : '<li>No se registraron palabras clave documentales.</li>'}
        ${(documentEvidence.snippet_text ? [`<li>Fragmento observado: ${documentEvidence.snippet_text}</li>`] : []).join('') || ''}
      </ul>
    </div>

    <div class="detail-box">
      <strong>Prueba de respaldo del score</strong>
      <ul class="evidence-list">
        ${(evidenceSignals && evidenceSignals.length) ? evidenceSignals.map((signal) => `<li>${signal}</li>`).join('') : '<li>Sin señales registradas.</li>'}
      </ul>
    </div>
  `;
}

searchInput.addEventListener('input', () => {
  loadSummary();
});

refreshBtn.addEventListener('click', loadSummary);

loadSummary();
setInterval(loadSummary, 15000);
