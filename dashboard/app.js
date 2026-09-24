const kpisRoot = document.getElementById('kpis');
const scoreChart = document.getElementById('scoreChart');
const scoreDefinition = document.getElementById('scoreDefinition');
const recordsTable = document.getElementById('recordsTable');
const weaknessList = document.getElementById('weaknessList');
const statusCard = document.getElementById('statusCard');
const riskSummary = document.getElementById('riskSummary');
const searchInput = document.getElementById('searchInput');
const refreshBtn = document.getElementById('refreshBtn');
const runAllBtn = document.getElementById('runAllBtn');
const statusFilter = document.getElementById('statusFilter');
const recordsSummary = document.getElementById('recordsSummary');
const lastUpdated = document.getElementById('lastUpdated');
const statusToast = document.getElementById('statusToast');
const jobPanel = document.getElementById('jobPanel');
const jobTitle = document.getElementById('jobTitle');
const jobStatus = document.getElementById('jobStatus');
const jobLog = document.getElementById('jobLog');
const jobUpdates = document.getElementById('jobUpdates');
const jobUpdatesList = document.getElementById('jobUpdatesList');
const jobProgressBar = document.getElementById('jobProgressBar');
const jobProgressText = document.getElementById('jobProgressText');
const jobDecision = document.getElementById('jobDecision');
const jobCandidates = document.getElementById('jobCandidates');
let activeJobId = null;
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
  showToast('Cargando resultados...', 'info');
  try {
    const res = await fetch('/api/summary', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderSummary(data);
    const stamp = new Date().toLocaleString('es-ES');
    lastUpdated.textContent = `Última actualización: ${stamp}`;
    hideToast();
    return data;
  } catch (error) {
    lastUpdated.textContent = 'No se pudieron cargar los resultados nuevos';
    console.error('Error cargando resumen:', error);
    showToast('Error cargando resumen. Revisa la consola.', 'error');
    return null;
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
  const filter = statusFilter ? statusFilter.value : 'all';
  const classifyRecord = (row) => {
    const mapped = Boolean(row.mapping_resolved || row.resolved_from_variant || row.mapped_from);
    const httpStatus = String(row.HTTP_Status || '').toUpperCase();
    if (httpStatus === 'PENDING') return 'pending';
    const failed = Boolean(row.Error_Detail) || ['CONN_ERROR', 'DNS_ERROR', 'SSL_ERROR', 'TIMEOUT', 'ROBOTS_BLOCKED'].includes(httpStatus);
    const score = Number(row.Score_Excel || 0);
    if (mapped && !failed) return 'alternative';
    if (failed) return 'review';
    if (score > 0) return 'success';
    return 'review';
  };
  const filtered = records.filter((row) => {
    const haystack = `${row.Fuente || ''} ${row.Url_Original || ''} ${row.Institucion || ''}`.toLowerCase();
    return haystack.includes(term) && (filter === 'all' || classifyRecord(row) === filter);
  });

  const counts = records.reduce((result, row) => {
    result[classifyRecord(row)] += 1;
    return result;
  }, { success: 0, alternative: 0, review: 0, pending: 0 });
  if (recordsSummary) {
    recordsSummary.innerHTML = [
      `<span class="summary-chip success"><strong>${counts.success}</strong> encontradas</span>`,
      `<span class="summary-chip alternative"><strong>${counts.alternative}</strong> resueltas por alternativa</span>`,
      `<span class="summary-chip review"><strong>${counts.review}</strong> requieren revisión</span>`,
      `<span class="summary-chip pending"><strong>${counts.pending}</strong> pendientes</span>`
    ].join('');
  }

  recordsTable.innerHTML = filtered.map((row) => {
    const score = Number(row.Score_Excel || 0);
    const recordState = classifyRecord(row);
    const label = recordState === 'alternative' ? 'Éxito con alternativa' : (recordState === 'success' ? 'Éxito' : (recordState === 'pending' ? 'Pendiente' : 'Revisión'));
    const badge = recordState === 'review' ? 'warning' : (recordState === 'pending' ? 'neutral' : 'success');
    const rowUrl = row.Url_Original || row.url || '';
    const isSelected = selectedUrl && rowUrl === selectedUrl;

    const mapStatus = row.mapping_status || 'none';
    const statusIcon = mapStatus === 'accepted' ? '✔' : (mapStatus === 'rejected' ? '✖' : (mapStatus === 'pending' ? '◌' : ''));
    const mapLabel = mapStatus === 'accepted' ? 'Aceptado' : (mapStatus === 'rejected' ? 'Rechazado' : (mapStatus === 'pending' ? 'Pendiente' : ''));
    const analysisState = classifyRecord(row);
    const stateLabel = analysisState === 'alternative' ? 'Alternativa encontrada' : (analysisState === 'success' ? 'URL encontrada' : (analysisState === 'pending' ? 'Pendiente' : 'No encontrada'));
    const stateClass = analysisState === 'alternative' ? 'alternative' : (analysisState === 'success' ? 'success' : (analysisState === 'pending' ? 'pending' : 'review'));
    const stateDetail = analysisState === 'alternative' ? 'Validar mapeo' : (analysisState === 'success' ? 'Acceso directo' : (analysisState === 'pending' ? 'Aún no analizada' : (row.Error_Detail || row.HTTP_Status || 'Buscar alternativa')));
    const alternativeButton = analysisState === 'review' && ['CONN_ERROR', 'DNS_ERROR', 'SSL_ERROR', 'TIMEOUT'].includes(String(row.HTTP_Status || '').toUpperCase())
      ? '<button class="small alternative-action" data-action="probe-alternatives">Probar URL alternativas</button>'
      : '';

    return `
      <tr data-url="${rowUrl.replace(/"/g, '&quot;')}" data-original="${(row.Url_Original||row.url||'').replace(/"/g, '&quot;')}" data-mapping-resolved="${String(row.mapping_resolved||row.Final_Url||'').replace(/"/g, '&quot;')}" class="${isSelected ? 'row-selected' : ''}" style="cursor:pointer;">
        <td>${row.Fuente || '-'}</td>
        <td><a href="${rowUrl || '#'}" target="_blank" rel="noreferrer">${rowUrl || '-'}</a></td>
        <td>${row.mapping_resolved || row.Final_Url || '-'}</td>
        <td class="mapping-cell" data-status="${mapStatus}"><span title="${mapLabel}">${statusIcon}</span></td>
        <td><span class="analysis-state ${stateClass}">${stateLabel}</span><small class="state-detail">${stateDetail}</small></td>
        <td>${formatScore(score)}</td>
        <td>${row.HTTP_Status || '-'}</td>
        <td><span class="badge ${badge}">${label}</span></td>
        <td class="row-actions">
          ${alternativeButton}
          <button class="small" data-action="run-url">Ejecutar</button>
        </td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="9">No se encontraron registros.</td></tr>';

  // Use event delegation on tbody for reliable, immediate selection
  recordsTable.querySelectorAll('tr[data-url]').forEach((el) => el.setAttribute('tabindex', '0'));

  // remove any existing delegated handlers to avoid duplicates
  recordsTable.replaceWith(recordsTable.cloneNode(true));
  const newTableBody = document.getElementById('recordsTable');

  newTableBody.addEventListener('click', async (ev) => {
    const alternativesBtn = ev.target.closest('button[data-action="probe-alternatives"]');
    if (alternativesBtn) {
      ev.stopPropagation();
      const row = alternativesBtn.closest('tr[data-url]');
      const urlToProbe = row?.getAttribute('data-original') || row?.getAttribute('data-url');
      if (!urlToProbe) return;
      alternativesBtn.disabled = true;
      alternativesBtn.innerHTML = '<span class="spinner-small"></span> Probando...';
      try {
        const response = await fetch('/api/probe_alternatives', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: urlToProbe })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        showJobPanel(payload.job_id, urlToProbe);
        await pollJob(payload.job_id);
      } catch (error) {
        console.error('alternative probe failed', error);
        showToast('No se pudieron probar las alternativas. Revisa el panel.', 'error');
      } finally {
        alternativesBtn.disabled = false;
        alternativesBtn.textContent = 'Probar URL alternativas';
      }
      return;
    }
    // If clicked a per-row action (run-url)
    const runBtn = ev.target.closest('button[data-action="run-url"]');
    if (runBtn) {
      ev.stopPropagation();
      const trRun = runBtn.closest('tr[data-url]');
      if (!trRun) return;
      const urlToRun = trRun.getAttribute('data-original') || trRun.getAttribute('data-url');
      if (!confirm(`¿Ejecutar análisis para ${urlToRun}?`)) return;

      // read current displayed score to detect change
      const tds = trRun.querySelectorAll('td');
      const scoreCell = tds[4];
      const beforeScore = scoreCell ? parseFloat((scoreCell.textContent || '').trim()) : null;

      runBtn.disabled = true;
      const originalText = runBtn.textContent;
      runBtn.innerHTML = '<span class="spinner-small"></span> Analizando...';

      try {
        const res = await fetch('/api/run_url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: urlToRun })
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const payload = await res.json();
        showToast('Análisis iniciado. Mostrando etapas y diagnóstico...', 'info', 0);
        showJobPanel(payload.job_id, urlToRun);
        pollJob(payload.job_id).then(() => {
          runBtn.disabled = false;
          runBtn.textContent = originalText;
        }).catch((error) => {
          console.error('pollRow error', error);
          runBtn.disabled = false;
          runBtn.textContent = originalText;
          showToast('Error durante el análisis. Revisa el panel de diagnóstico.', 'error');
        });

      } catch (err) {
        console.error('run_url failed', err);
        showToast('No se pudo solicitar el análisis para esta URL. Revisa la consola.', 'error');
        runBtn.disabled = false;
        runBtn.textContent = originalText;
      }
      return;
    }

    // If click inside mapping-cell, handle accept/reject directly
    const mappingCell = ev.target.closest('.mapping-cell');
    if (mappingCell) {
      ev.stopPropagation();
      const trMap = mappingCell.closest('tr[data-url]');
      if (!trMap) return;
      const status = mappingCell.getAttribute('data-status');
      if (status !== 'pending') {
        // only allow action on pending mappings
        return;
      }
      const original = trMap.getAttribute('data-original');
      const resolved = trMap.getAttribute('data-mapping-resolved');
      const accept = confirm('¿Aceptar mapeo para esta fila? (Aceptar = aceptar, Cancelar = rechazar)');
      const action = accept ? 'accept' : 'reject';
      fetch(`/api/mapping/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original: original, resolved: resolved })
      }).then((res) => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        loadSummary();
      }).catch((err) => {
        console.error('Mapping action error', err);
        alert('No se pudo ejecutar la acción de mapeo. Ver consola.');
      });
      return;
    }

    const tr = ev.target.closest('tr[data-url]');
    if (!tr) return;
    // immediate visual feedback
    newTableBody.querySelectorAll('tr.row-selected').forEach((el) => el.classList.remove('row-selected'));
    tr.classList.add('row-selected');
    // ensure the clicked row is visible
    try { tr.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) { /* ignore */ }

    const url = tr.getAttribute('data-url');
    selectedUrl = url || null;
    const selected = records.find((item) => {
      const candidate = item.Url_Original || item.url || '';
      return candidate === url;
    });
    showRecordEvidence(selected || null);
  });

  // keyboard interaction: Enter/Space on focused row
  newTableBody.addEventListener('keydown', (ev) => {
    const tr = ev.target.closest && ev.target.closest('tr[data-url]');
    if (!tr) return;
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      tr.click();
    }
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
  const documentEvidence = evidenceFromRecord.document_evidence || record.Document_Evidence || record.document_evidence || {};
  const evidenceSignals = (evidenceFromRecord.signals || record.signals || []);

  const rawScore = Number(record.Score_Excel || 0);
  const effectiveScore = Number(evidenceFromRecord.score || documentEvidence.quality_score || 0);
  const capped = rawScore > effectiveScore && effectiveScore <= 2.0;
  const diagnostics = Array.isArray(record.Diagnosticos_Excel) ? record.Diagnosticos_Excel : [];
  const scoreReasons = buildScoreReason(record, rawScore, effectiveScore);
  const evidenceLists = buildEvidenceLists(record);

  const docSamples = (documentEvidence.samples && documentEvidence.samples.length) ? documentEvidence.samples : (
    Number(record.Doc_Links_Found_In_Seed || 0) > 0 ? [
      {
        title: `Enlace directo a documentos e informes (${record.Fuente || 'Fuente'})`,
        url: record.Final_Url || record.Url_Original || '#',
        file_type: documentEvidence.file_type || 'DOC'
      }
    ] : []
  );

  const snippetText = (documentEvidence.snippet_text && documentEvidence.snippet_text.trim() !== '.') ? documentEvidence.snippet_text : (
    (Number(record.Doc_Links_Found_In_Seed || 0) > 0 || (documentEvidence.keyword_hits || []).length > 0)
      ? `Página observada con respuesta HTTP ${record.HTTP_Status || 200}. Se detectaron ${record.Doc_Links_Found_In_Seed || 0} enlaces a documentos e indicadores sobre: ${(documentEvidence.keyword_hits || []).join(', ')}.`
      : 'Página observada sin fragmento de texto adicional.'
  );

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

    <!-- Resolved URL / mapping controls -->
    <div class="detail-grid">
      <div class="detail-box detail-box-wide">
          <strong>Resolved URL</strong>
          ${record.mapping_resolved || record.Final_Url || '-'}
        </div>
      <div class="detail-box">
          ${record.mapping_resolved ? `
            <strong>Mapeo automático</strong>
            <div>Detectado desde: ${record.original_url || record.mapped_from || record.Url_Original || '-'}</div>
            <div style="margin-top:8px;">
              <input id="resolvedInput" type="text" value="${(record.mapping_resolved || record.Final_Url || '').replace(/"/g, '&quot;')}" style="width:100%; margin-bottom:6px;" />
              <div>
                <button id="acceptMapping" class="primary-btn small">Aceptar mapeo</button>
                <button id="rejectMapping" class="secondary-btn small">Rechazar mapeo</button>
              </div>
            </div>
          ` : ''}
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
      <ul class="evidence-list" style="margin-bottom:10px;">
        ${(documentEvidence.keyword_hits || []).length ? documentEvidence.keyword_hits.map((hit) => `<li>Palabra clave documental: ${hit}</li>`).join('') : '<li>No se registraron palabras clave documentales.</li>'}
      </ul>

      ${(docSamples && docSamples.length) ? `
        <div style="margin-top:10px; margin-bottom:10px;">
          <strong style="font-size:0.82rem; color:#475569; text-transform:uppercase; letter-spacing:0.04em;">Muestra de documentos / reportes directos (${docSamples.length}):</strong>
          <div style="display:flex; flex-direction:column; gap:6px; margin-top:6px;">
            ${docSamples.map((s) => `
              <div style="display:flex; align-items:center; justify-content:space-between; background:#f8fafc; border:1px solid #e2e8f0; padding:6px 10px; border-radius:6px; font-size:0.85rem;">
                <div style="display:flex; align-items:center; gap:8px; overflow:hidden;">
                  <span style="background:${s.file_type === 'PDF' ? '#ef4444' : s.file_type === 'XLSX' ? '#10b981' : '#3b82f6'}; color:white; font-size:0.7rem; font-weight:700; padding:2px 6px; border-radius:4px;">${s.file_type || 'DOC'}</span>
                  <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:320px; font-weight:500;" title="${s.title}">${s.title}</span>
                </div>
                <a href="${s.url}" target="_blank" rel="noreferrer" class="secondary-btn small" style="text-decoration:none; font-size:0.75rem; padding:3px 8px;">🔗 Abrir enlace</a>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${snippetText ? `
        <div style="margin-top:10px; background:#f1f5f9; border-left:4px solid #0284c7; padding:10px; border-radius:0 6px 6px 0; font-size:0.85rem; color:#334155; line-height:1.4;">
          <strong style="color:#0369a1;">📝 Vista previa del contenido documentado:</strong><br/>
          <em>"${snippetText}"</em>
        </div>
      ` : ''}
    </div>

    <div class="detail-box">
      <strong>Prueba de respaldo del score</strong>
      <ul class="evidence-list">
        ${(evidenceSignals && evidenceSignals.length) ? evidenceSignals.map((signal) => `<li>${signal}</li>`).join('') : '<li>Sin señales registradas.</li>'}
      </ul>
    </div>
  `;

  // Attach mapping accept/reject handlers if present
  const acceptBtn = document.getElementById('acceptMapping');
  const rejectBtn = document.getElementById('rejectMapping');
  if (acceptBtn || rejectBtn) {
    const original = record.original_url || record.mapped_from || record.Url_Original || record.Url_Original;
    const resolved = record.final_url || record.Final_Url;

    async function postAction(action) {
      try {
        const input = document.getElementById('resolvedInput');
        const resolvedValue = input ? input.value.trim() : resolved;
        const res = await fetch(`/api/mapping/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ original: original, resolved: resolvedValue })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // reload summary to reflect mapping decision
        await loadSummary();
      } catch (err) {
        console.error('Mapping action failed', err);
        alert('No se pudo registrar la decisión de mapeo. Revisa la consola.');
      }
    }

    if (acceptBtn) acceptBtn.addEventListener('click', () => postAction('accept'));
    if (rejectBtn) rejectBtn.addEventListener('click', () => postAction('reject'));
  }
}

searchInput.addEventListener('input', () => {
  loadSummary();
});
if (statusFilter) statusFilter.addEventListener('change', () => loadSummary());

refreshBtn.addEventListener('click', async () => {
  try {
    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Cargando...';
    await loadSummary();
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = 'Actualizar';
  }
});
if (runAllBtn) {
  runAllBtn.addEventListener('click', async () => {
    if (!confirm('¿Ejecutar el análisis completo para todas las URLs ahora? Esto puede tardar.')) return;
    try {
      const before = await loadSummary();
      const beforeCount = before ? before.total_records : 0;
      const res = await fetch('/api/run_all', { method: 'POST' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const payload = await res.json();
      const jobId = payload.job_id;
      showToast('Actualización iniciada. Las URLs se analizarán una por una.', 'info', 4000);
      runAllBtn.disabled = true;
      const originalText = runAllBtn.textContent;
      runAllBtn.innerHTML = '<span class="spinner-small"></span> Ejecutando...';
      showJobPanel(jobId);
      pollJob(jobId).then(() => {
        runAllBtn.disabled = false;
        runAllBtn.textContent = originalText;
      }).catch((e) => {
        console.error('job poll error', e);
        showToast(e.message || 'La actualización se interrumpió. Revisa los logs.', 'error');
        runAllBtn.disabled = false;
        runAllBtn.textContent = originalText;
      });
    } catch (err) {
      console.error('run_all failed', err);
      showToast('No se pudo iniciar el análisis completo. Revisa la consola.', 'error');
      runAllBtn.disabled = false;
      runAllBtn.textContent = 'Ejecutar análisis (todo)';
    }
  });
}

loadSummary();
setInterval(loadSummary, 15000);

function showJobPanel(jobId, targetUrl = '') {
  activeJobId = jobId;
  if (!jobPanel) return;
  jobPanel.style.display = 'flex';
  jobTitle.textContent = targetUrl ? 'Análisis de URL' : 'Actualización de URLs';
  jobStatus.textContent = 'Preparando análisis...';
  jobLog.textContent = 'Sin eventos todavía.';
  jobProgressText.textContent = '0 URLs procesadas';
  jobProgressBar.style.width = '0%';
  const jobGeminiVerdict = document.getElementById('jobGeminiVerdict');
  if (jobGeminiVerdict) {
    jobGeminiVerdict.style.display = 'none';
    jobGeminiVerdict.innerHTML = '';
  }
  jobDecision.style.display = 'none';
  jobDecision.innerHTML = '';
  jobCandidates.style.display = 'none';
  jobCandidates.innerHTML = '';
  jobUpdates.style.display = 'none';
  jobUpdatesList.innerHTML = '';
}

async function pollJob(jobId) {
  const startedAt = Date.now();
  while (activeJobId === jobId) {
    const [statusRes, logsRes, updatesRes] = await Promise.all([
      fetch(`/api/job/${jobId}`, { cache: 'no-store' }),
      fetch(`/api/job/${jobId}/logs`, { cache: 'no-store' }),
      fetch(`/api/job/${jobId}/updates`, { cache: 'no-store' })
    ]);
    if (!statusRes.ok) {
      throw new Error(statusRes.status === 404 ? 'El job ya no está disponible. Revisa output/jobs o inicia una nueva actualización.' : `HTTP ${statusRes.status}`);
    }
    const status = await statusRes.json();
    const logs = logsRes.ok ? await logsRes.json() : { logs: '' };
    const updates = updatesRes.ok ? await updatesRes.json() : { updated: [] };
    const progress = Number(status.tested ?? status.progress ?? 0);
    const total = Number(status.total || 0);
    jobStatus.textContent = status.stage_detail || (status.status === 'finished' ? 'Análisis completado' : 'Analizando URL por URL');
    jobStatus.className = status.status === 'failed' || status.error_detail ? 'job-status-error' : 'job-status-active';
    jobProgressBar.style.width = `${total ? Math.min(100, (progress / total) * 100) : 0}%`;
    jobProgressText.textContent = total ? `${progress} de ${total} alternativas probadas` : 'Preparando lista de URLs...';
    if (status.type === 'probe_alternatives' && Array.isArray(status.alternatives) && status.alternatives.length) {
      const testedItems = status.alternatives.slice().reverse().map((item) => {
        const sourceLabel = item.source === 'gemini' ? 'Gemini' : 'Variante local';
        return `
          <div class="candidate-row ${item.reachable ? 'candidate-ok' : 'candidate-failed'}">
            <span class="candidate-mark">${item.reachable ? 'OK' : 'x'}</span>
            <span class="candidate-url">${item.url}</span>
            <span class="candidate-result">${item.reachable ? `HTTP ${item.status}` : item.reason} · ${sourceLabel}</span>
          </div>
        `;
      }).join('');
      jobCandidates.style.display = 'block';
      jobCandidates.innerHTML = `<div class="candidate-heading">URLs probadas (${status.alternatives.length}/${total || status.alternatives.length})</div><div class="candidate-list">${testedItems}</div>`;
    }
    if (status.type === 'probe_alternatives') {
      const verdict = status.gemini_verdict || {};
      const jobGeminiVerdict = document.getElementById('jobGeminiVerdict');
      
      let verdictHtml = '';
      if (verdict.status && verdict.status !== 'skipped' && verdict.reason) {
        const bestUrlText = verdict.best_url ? ` <br/><strong style="font-size:0.95rem; color:#0d6efd;">Nueva URL sugerida: ${verdict.best_url}</strong>` : '';
        const badgeColor = verdict.status === 'moved' ? '#0f5132' : (verdict.status === 'not_found' ? '#842029' : '#055160');
        const badgeBg = verdict.status === 'moved' ? '#d1e7dd' : (verdict.status === 'not_found' ? '#f8d7da' : '#cff4fc');
        const statusLabel = verdict.status === 'moved' ? 'SITIO MIGRADO' : (verdict.status === 'not_found' ? 'SITIO O RECURSO NO EXISTE' : 'DIAGNÓSTICO DE IA');
        
        const summary = verdict.status === 'moved'
          ? `La IA determinó que este portal migró a una nueva dirección web.${bestUrlText}<br/><em>Diagnóstico: ${verdict.reason || ''}</em>`
          : verdict.status === 'not_found'
            ? `La IA determinó que esta institución o recurso web de plano ya no existe.<br/><em>Explicación: ${verdict.reason || ''}</em>`
            : `Diagnóstico de la IA:<br/><em>${verdict.reason || ''}</em>${bestUrlText}`;
        
        let actionBtn = '';
        if (verdict.best_url) {
          actionBtn = `<div style="margin-top:10px;"><button id="analyzeBestGeminiBtn" class="primary-btn small">Analizar URL migrada sugerida por IA (${verdict.best_url})</button></div>`;
        }

        let alternativesBtns = '';
        if (Array.isArray(verdict.alternatives) && verdict.alternatives.length) {
          const list = verdict.alternatives.map((alt) => `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:6px; background:rgba(255,255,255,0.7); padding:6px 10px; border-radius:4px;">
              <span style="font-family:monospace; font-size:0.85rem;">${alt}</span>
              <button class="secondary-btn small analyze-alt-direct-btn" data-url="${alt}">Analizar esta opción</button>
            </div>
          `).join('');
          alternativesBtns = `<div style="margin-top:10px;"><strong>Otras URLs encontradas por la IA:</strong>${list}</div>`;
        }

        verdictHtml = `
          <div class="gemini-card" style="background:${badgeBg}; color:${badgeColor}; border-radius:8px; padding:14px; margin-bottom:12px; border:1px solid rgba(0,0,0,0.1);">
            <div style="font-weight:700; font-size:0.95rem; margin-bottom:6px;">🤖 Veredicto IA (Gemini): ${statusLabel}</div>
            <div style="line-height:1.4;">${summary}</div>
            ${actionBtn}
            ${alternativesBtns}
          </div>
        `;
      } else if (status.status === 'finished') {
        verdictHtml = `
          <div class="gemini-card" style="background:#e2e3e5; color:#41464b; border-radius:8px; padding:12px; margin-bottom:12px;">
            <div style="font-weight:600;">🤖 Diagnóstico de IA</div>
            <div>Consultando estado de migración con la IA de Gemini...</div>
          </div>
        `;
      }

      if (jobGeminiVerdict && verdictHtml) {
        jobGeminiVerdict.style.display = 'block';
        jobGeminiVerdict.innerHTML = verdictHtml;

        if (verdict.best_url) {
          const btn = document.getElementById('analyzeBestGeminiBtn');
          if (btn) {
            btn.onclick = async () => {
              btn.disabled = true;
              btn.textContent = 'Iniciando análisis...';
              const response = await fetch('/api/run_url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: verdict.best_url, original_url: status.target_url })
              });
              if (!response.ok) throw new Error(`HTTP ${response.status}`);
              const nextJob = await response.json();
              showJobPanel(nextJob.job_id, verdict.best_url);
              pollJob(nextJob.job_id).catch((error) => console.error('analysis failed', error));
            };
          }
        }

        document.querySelectorAll('.analyze-alt-direct-btn').forEach((btn) => {
          btn.onclick = async () => {
            const targetAlt = btn.getAttribute('data-url');
            if (!targetAlt) return;
            btn.disabled = true;
            btn.textContent = 'Analizando...';
            const response = await fetch('/api/run_url', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url: targetAlt, original_url: status.target_url })
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const nextJob = await response.json();
            showJobPanel(nextJob.job_id, targetAlt);
            pollJob(nextJob.job_id).catch((error) => console.error('analysis failed', error));
          };
        });
      }
    }
    if (status.status === 'awaiting_confirmation' && status.alternative_url) {
      jobProgressText.textContent = 'Alternativa lista para revisar';
      jobDecision.style.display = 'flex';
      jobDecision.innerHTML = `<span>Se sugiere: <strong>${status.alternative_url}</strong></span><button id="confirmAlternative" class="primary-btn small">Analizar alternativa</button>`;
      document.getElementById('confirmAlternative').onclick = async () => {
        jobDecision.querySelector('button').disabled = true;
        jobDecision.querySelector('button').textContent = 'Confirmando...';
        await fetch('/api/run_url/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job_id: jobId }) });
      };
    }
    const errorMessage = status.error_detail ? `\n\nMotivo técnico: ${status.error_detail}` : '';
    jobLog.textContent = (logs.logs || 'Esperando eventos del crawler...') + errorMessage;
    if (updates.updated && updates.updated.length) {
      jobUpdates.style.display = 'block';
      jobUpdatesList.innerHTML = updates.updated.map((url) => `<li>${url}</li>`).join('');
    }
    if (Array.isArray(status.alternatives) && status.alternatives.length && status.type === 'probe_alternatives') {
      const alternatives = status.alternatives.slice().sort((left, right) => Number(right.reachable) - Number(left.reachable));
      const options = alternatives.map((item, index) => `<option class="${item.reachable ? 'found-option' : ''}" value="${index}">${item.reachable ? 'ENCONTRADA' : 'No disponible'} | HTTP ${item.status || '-'} | ${item.url}</option>`).join('');
      const foundCount = alternatives.filter((item) => item.reachable).length;
      jobDecision.style.display = 'block';
      jobDecision.innerHTML = `<strong>Encontradas primero (${foundCount})</strong><select id="alternativeSelect">${options}</select><div id="alternativeReason" class="alternative-reason"></div><div class="alternative-actions"><button id="autoAnalyzeAlternatives" class="primary-btn small" ${foundCount ? '' : 'disabled'}>Analizar encontradas automáticamente</button><button id="analyzeSelectedAlternative" class="secondary-btn small">Analizar seleccionada</button></div>`;
      const alternativeSelect = document.getElementById('alternativeSelect');
      const reason = document.getElementById('alternativeReason');
      const updateReason = () => {
        const item = alternatives[Number(alternativeSelect.value)];
        reason.textContent = item ? `${item.reachable ? 'Accesible' : 'Falló'}: ${item.reason}` : '';
      };
      alternativeSelect.onchange = updateReason;
      updateReason();
      document.getElementById('autoAnalyzeAlternatives').onclick = async () => {
        const button = document.getElementById('autoAnalyzeAlternatives');
        button.disabled = true;
        button.textContent = 'Analizando encontradas...';
        const response = await fetch('/api/analyze_alternatives', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_url: status.target_url, alternatives: alternatives.filter((item) => item.reachable) }) });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const nextJob = await response.json();
        showJobPanel(nextJob.job_id, status.target_url);
        pollJob(nextJob.job_id).catch((error) => console.error('automatic alternative analysis failed', error));
      };
      document.getElementById('analyzeSelectedAlternative').onclick = async () => {
        const item = alternatives[Number(alternativeSelect.value)];
        if (!item || !item.url) return;
        const response = await fetch('/api/run_url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: item.url, original_url: status.target_url }) });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const nextJob = await response.json();
        showJobPanel(nextJob.job_id, item.url);
        pollJob(nextJob.job_id).catch((error) => console.error('alternative analysis failed', error));
      };
    }
    if (Array.isArray(status.analysis_results) && status.analysis_results.length && status.type === 'analyze_alternatives') {
      const options = status.analysis_results.map((item, index) => `<option value="${index}">#${index + 1} | ${item.url} | relevancia ${item.relevance} | docs ${item.document_links} | keywords ${item.keyword_hits.length}</option>`).join('');
      jobDecision.style.display = 'block';
      jobDecision.innerHTML = `<strong>Ranking de alternativas</strong><select id="rankedAlternativeSelect">${options}</select><div class="alternative-reason">Orden: documentos detectados, palabras clave y score.</div><button id="applyRankedAlternative" class="primary-btn small">Usar alternativa seleccionada</button>`;
      document.getElementById('applyRankedAlternative').onclick = async () => {
        const selected = status.analysis_results[Number(document.getElementById('rankedAlternativeSelect').value)];
        const response = await fetch('/api/apply_alternative', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_url: status.target_url, selected }) });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        await loadSummary();
        await loadData();
        showToast('Alternativa aplicada. La fila ahora usa la URL accesible.', 'info');
      };
    }
      if (status.type === 'run_url' && (status.status === 'finished' || status.status === 'completed')) {
      const resolvedUrl = status.alternative_url || status.target_url;
      const origUrl = status.mapped_from || status.original_url || status.target_url;
      jobDecision.style.display = 'block';
      jobDecision.innerHTML = `
        <div style="background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; padding:14px; margin-top:8px;">
          <div style="font-weight:700; color:#0369a1; font-size:0.95rem; margin-bottom:6px;">
            🎉 Análisis Finalizado para: <span style="font-family:monospace; font-weight:600;">${resolvedUrl}</span>
          </div>
          <div style="font-size:0.9rem; color:#334155; margin-bottom:10px; line-height:1.4;">
            ${status.error_detail 
              ? `⚠️ La URL fue probada pero presentó observación de red (<strong>${status.error_detail}</strong>). Puedes forzar su mapeo si deseas conservar esta dirección.` 
              : `✅ La URL respondió y fue validada exitosamente.`}
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button id="applyRunUrlBtn" class="primary-btn small">✅ Guardar URL y Actualizar Dashboard</button>
            <button id="reprobeAlternativesBtn" class="secondary-btn small">🔍 Probar otras alternativas con IA</button>
          </div>
        </div>
      `;
      const applyBtn = document.getElementById('applyRunUrlBtn');
      if (applyBtn) {
        applyBtn.onclick = async () => {
          applyBtn.disabled = true;
          applyBtn.textContent = 'Guardando...';
          const resp = await fetch('/api/apply_alternative', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ original_url: origUrl, resolved_url: resolvedUrl })
          });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          await loadSummary();
          await loadData();
          showToast(`URL ${resolvedUrl} mapeada correctamente.`, 'info');
          jobPanel.style.display = 'none';
        };
      }
      const reprobeBtn = document.getElementById('reprobeAlternativesBtn');
      if (reprobeBtn) {
        reprobeBtn.onclick = async () => {
          reprobeBtn.disabled = true;
          reprobeBtn.textContent = 'Iniciando búsqueda con IA...';
          const response = await fetch('/api/probe_alternatives', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: origUrl })
          });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const nextJob = await response.json();
          showJobPanel(nextJob.job_id, origUrl);
          pollJob(nextJob.job_id).catch((err) => console.error('probe failed', err));
        };
      }
    }
    if (status.status === 'finished' || status.status === 'failed') {
      await loadSummary();
      await loadData();
      showToast(status.error_detail ? `Análisis terminado: ${status.error_detail}` : 'Análisis terminado.', status.error_detail ? 'warn' : 'info');
      return status;
    }
    if (Date.now() - startedAt > 30 * 60 * 1000) {
      throw new Error('El análisis superó el tiempo máximo de 30 minutos. Revisa los logs antes de volver a iniciarlo.');
    }
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
  return null;
}

document.getElementById('jobClose')?.addEventListener('click', () => {
  activeJobId = null;
  jobPanel.style.display = 'none';
});
document.getElementById('jobRefresh')?.addEventListener('click', () => {
  if (activeJobId) pollJob(activeJobId).catch((error) => console.error('job poll error', error));
});

function showToast(msg, level = 'info', timeout = 7000) {
  if (!statusToast) return;
  statusToast.textContent = msg;
  statusToast.className = `toast show ${level}`;
  statusToast.style.display = 'block';
  if (timeout) {
    setTimeout(() => {
      hideToast();
    }, timeout);
  }
}

function hideToast() {
  if (!statusToast) return;
  statusToast.className = 'toast';
  setTimeout(() => {
    statusToast.style.display = 'none';
  }, 220);
}

refreshBtn?.addEventListener('click', () => {
  loadSummary();
});

loadSummary();
