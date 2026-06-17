#!/usr/bin/env python3
"""
VoiceBM Web Dashboard - Professional UI with branding
LLM Voice Biometrics by David M. Dryver Sr.

Provides web interface for VoiceBM control, enrollment, clustering, and blocklist management.
File-based shared state for multi-platform support (Home Assistant, Open WebUI, local LLM).
"""

from flask import Flask, render_template_string, jsonify, request, send_file
from flask_cors import CORS
from pathlib import Path
import json
import os
import sys
import tempfile
from typing import Dict, List, Optional
import datetime
import paho.mqtt.publish as mqtt_publish

# VoiceBM config helpers — config.json is the single source of truth for the
# ID Injection and Transcript Preferred switches. Both dashboard and HA read/write it.
sys.path.insert(0, "/home/user/voicebm")
sys.path.insert(0, "/home/user/voicebm/bin")
from voicebm_config import (
    get_mqtt_config,
    get_inject_identity,
    get_transcript_preferred,
    update_voicebm_config_key,
)

app = Flask(__name__)
CORS(app)

# Configuration
VOICEBM_BASE = "/home/user/voicebm"
META_DIR = f"{VOICEBM_BASE}/meta"
ENROLL_DIR = f"{VOICEBM_BASE}/enroll"
PENDING_RECORDINGS = f"{VOICEBM_BASE}/pending_active/recordings"
AUDIO_SERVER_BASE = "http://127.0.0.1:9090"

# MQTT — retained state publishes so HA reflects dashboard-side switch changes.
_MQTT = get_mqtt_config()


def publish_retained(topic: str, payload: str):
    """Publish a single retained message to the broker (fire-and-forget)."""
    try:
        auth = None
        if _MQTT.get("user"):
            auth = {"username": _MQTT["user"], "password": _MQTT.get("password", "")}
        mqtt_publish.single(
            topic,
            payload=payload,
            qos=1,
            retain=True,
            hostname=_MQTT["broker"],
            port=_MQTT["port"],
            auth=auth,
            client_id="voicebm_dashboard_pub",
        )
    except Exception as e:
        print(f"[dashboard] MQTT publish failed for {topic}: {e}")


def publish_command(topic: str, payload: str):
    """Publish a one-shot command (NON-retained) — enrollment, reject, etc.
    Commands are actions, not state, so they must not be retained or they would
    replay on every broker reconnect."""
    try:
        auth = None
        if _MQTT.get("user"):
            auth = {"username": _MQTT["user"], "password": _MQTT.get("password", "")}
        mqtt_publish.single(
            topic,
            payload=payload,
            qos=1,
            retain=False,
            hostname=_MQTT["broker"],
            port=_MQTT["port"],
            auth=auth,
            client_id="voicebm_dashboard_cmd",
        )
    except Exception as e:
        print(f"[dashboard] MQTT command publish failed for {topic}: {e}")

# State files
SETTINGS_FILE = f"{META_DIR}/settings.json"
ACTIVE_STATE_FILE = f"{META_DIR}/active_state.json"
PENDING_FILE = f"{VOICEBM_BASE}/pending_active/pending.json"
CLUSTERS_FILE = f"{META_DIR}/clusters.json"
USER_SETTINGS_FILE = f"{META_DIR}/user_settings.json"
THING_ENGINE_COMMANDS_FILE = f"{META_DIR}/thing_engine_commands.json"
# The analyzer reads the active match threshold (MATCH_T_ACTIVE) live from this
# file on every request. The dashboard writes it directly here — no MQTT — so
# threshold control works for users with no broker (e.g. OpenWebUI-only).
THRESHOLD_FILE = f"{VOICEBM_BASE}/out/thresholds.json"

# HTML Template with Bootstrap tables and branding
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VoiceBM Control Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            background-color: #1a1a1a;
            color: #e0e0e0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
        }
        .main-container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .brand-header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .brand-title {
            font-size: 2.5rem;
            font-weight: bold;
            margin: 0;
            color: white;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .brand-author {
            font-size: 1.1rem;
            margin: 5px 0;
            color: rgba(255,255,255,0.9);
        }
        .brand-version {
            font-size: 0.9rem;
            color: rgba(255,255,255,0.7);
            font-style: italic;
        }
        .section-card {
            background-color: #2d2d2d;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .section-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: #4ade80;
            border-bottom: 2px solid #4ade80;
            padding-bottom: 8px;
        }
        .table-dark {
            background-color: #242424;
            color: #e0e0e0;
        }
        .table-dark thead {
            background-color: #1a1a1a;
        }
        .table-dark tbody tr:hover {
            background-color: #333;
        }
        .badge-virtual {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .badge-active {
            background-color: #4ade80;
        }
        .badge-blocked {
            background-color: #ef4444;
        }
        .btn-play { background-color: #3b82f6; border: none; }
        .btn-play:hover { background-color: #2563eb; }
        .btn-enroll { background-color: #10b981; border: none; }
        .btn-enroll:hover { background-color: #059669; }
        .btn-reject { background-color: #ef4444; border: none; }
        .btn-reject:hover { background-color: #dc2626; }
        .form-switch .form-check-input {
            width: 3em;
            height: 1.5em;
            cursor: pointer;
        }
        .form-switch .form-check-input:checked {
            background-color: #4ade80;
            border-color: #4ade80;
        }
        .cluster-card {
            background-color: #242424;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid #f59e0b;
        }
        .similarity-badge {
            background-color: #f59e0b;
            color: #000;
            font-weight: bold;
        }
        .no-activity {
            color: #60a5fa;
            font-style: italic;
        }
        .threshold-slider {
            width: 100%;
        }
        .badge-count {
            background-color: #6366f1;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <!-- Branded Header -->
        <div class="brand-header">
            <div class="brand-title">
                <i class="bi bi-mic-fill"></i> LLM Voice Biometrics
            </div>
            <div class="brand-author">by David M. Dryver Sr.</div>
            <div class="brand-version">Firmware: 2.0</div>
        </div>

        <!-- Active Pipeline Section -->
        <div class="section-card">
            <h2 class="section-title"><i class="bi bi-broadcast"></i> Active Pipeline</h2>
            <div id="active-status" class="no-activity">No recent activity</div>
            <div class="row mt-3">
                <div class="col-md-4">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="injectionToggle">
                        <label class="form-check-label" for="injectionToggle">
                            ID Injection: <span id="injectionStatus">OFF</span>
                        </label>
                    </div>
                    <div class="form-check form-switch mt-2">
                        <input class="form-check-input" type="checkbox" id="transcriptPreferredToggle">
                        <label class="form-check-label" for="transcriptPreferredToggle">
                            Transcript Preferred: <span id="transcriptPreferredStatus">OFF</span>
                        </label>
                    </div>
                </div>
                <div class="col-md-8">
                    <label for="thresholdSlider" class="form-label">
                        Active Threshold: <span id="thresholdValue">0.50</span>
                    </label>
                    <input type="range" class="form-range threshold-slider" id="thresholdSlider" 
                           min="0.01" max="1.00" step="0.01" value="0.50">
                </div>
            </div>
        </div>

        <!-- Blocklist Control Section -->
        <div class="section-card">
            <h2 class="section-title"><i class="bi bi-shield-lock"></i> Blocklist Control</h2>
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Identity</th>
                        <th>Status</th>
                        <th>Samples</th>
                        <th>Control</th>
                    </tr>
                </thead>
                <tbody id="blocklistTable">
                    <tr><td colspan="4" class="text-center">Loading...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Thing Engine Section -->
        <div class="section-card">
            <h2 class="section-title"><i class="bi bi-tools"></i> Thing Engine - Identity Management</h2>
            <p class="text-muted mb-3">Permanent identity operations: rename, merge, and delete enrolled identities.</p>
            
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Identity</th>
                        <th>Transform</th>
                        <th>Merge Tag</th>
                        <th>Delete</th>
                    </tr>
                </thead>
                <tbody id="thingEngineTable">
                    <tr><td colspan="4" class="text-center">Loading...</td></tr>
                </tbody>
            </table>
            
            <div class="mt-3">
                <button class="btn btn-warning" id="executeMergeBtn" disabled>
                    <i class="bi bi-arrow-down-up"></i> Merge Tagged Identities
                </button>
            </div>
        </div>

        <!-- Pending Voices Section -->
        <div class="section-card">
            <h2 class="section-title">
                <i class="bi bi-hourglass-split"></i> Pending Voices
                <span class="badge badge-count" id="pendingCount">0</span>
            </h2>
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Timestamp</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="pendingTable">
                    <tr><td colspan="3" class="text-center">No pending voices</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Enrolled Identities Section -->
        <div class="section-card">
            <h2 class="section-title">
                <i class="bi bi-people-fill"></i> Enrolled Identities
                <span class="badge badge-count" id="enrolledCount">0</span>
            </h2>
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Samples</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Personal Threshold</th>
                    </tr>
                </thead>
                <tbody id="enrolledTable">
                    <tr><td colspan="5" class="text-center">Loading...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Voice Clusters Section -->
        <div class="section-card">
            <h2 class="section-title">
                <i class="bi bi-diagram-3"></i> Voice Clusters
                <span class="badge badge-count" id="clusterCount">0</span>
            </h2>
            <div id="clustersList">
                <p class="text-center">No clusters available</p>
            </div>
        </div>
    </div>

    <script>
        // State
        let currentSettings = {};
        let currentActiveState = {};

        // Load initial state
        async function loadState() {
            try {
                const [settings, activeState, pending, clusters, enrolled] = await Promise.all([
                    fetch('/api/state/settings').then(r => r.json()),
                    fetch('/api/state/active').then(r => r.json()),
                    fetch('/api/state/pending').then(r => r.json()),
                    fetch('/api/state/clusters').then(r => r.json()),
                    fetch('/api/enrolled').then(r => r.json())
                ]);

                updateSettings(settings);
                updateActiveState(activeState);
                updatePending(pending);
                updateClusters(clusters);
                updateBlocklist(enrolled);
                updateEnrolled(enrolled);
                loadThingEngine();
            } catch (error) {
                console.error('Error loading state:', error);
            }
        }

        function updateSettings(settings) {
            currentSettings = settings;
            const injectionToggle = document.getElementById('injectionToggle');
            const injectionStatus = document.getElementById('injectionStatus');
            const thresholdSlider = document.getElementById('thresholdSlider');
            const thresholdValue = document.getElementById('thresholdValue');

            injectionToggle.checked = settings.inject_identity || false;
            injectionStatus.textContent = settings.inject_identity ? 'ON' : 'OFF';
            injectionStatus.style.color = settings.inject_identity ? '#4ade80' : '#ef4444';

            const transcriptPreferredToggle = document.getElementById('transcriptPreferredToggle');
            const transcriptPreferredStatus = document.getElementById('transcriptPreferredStatus');
            transcriptPreferredToggle.checked = settings.transcript_preferred || false;
            transcriptPreferredStatus.textContent = settings.transcript_preferred ? 'ON' : 'OFF';
            transcriptPreferredStatus.style.color = settings.transcript_preferred ? '#4ade80' : '#ef4444';

            const threshold = settings.active_threshold || 0.50;
            thresholdSlider.value = threshold;
            thresholdValue.textContent = threshold.toFixed(2);
        }

        function updateActiveState(state) {
            currentActiveState = state;
            const statusDiv = document.getElementById('active-status');
            
            if (state.speaker_id) {
                statusDiv.innerHTML = `
                    <strong>Current Speaker:</strong> ${state.display_name || 'Unknown'} 
                    (${state.speaker_id})<br>
                    <strong>Confidence:</strong> ${(state.confidence * 100).toFixed(1)}%<br>
                    <strong>Decision:</strong> <span class="badge ${state.decision === 'accepted' ? 'badge-active' : 'bg-warning'}">${state.decision}</span>
                `;
                statusDiv.classList.remove('no-activity');
            } else {
                statusDiv.innerHTML = 'No recent activity';
                statusDiv.classList.add('no-activity');
            }
        }

        function updatePending(pending) {
            const table = document.getElementById('pendingTable');
            const count = document.getElementById('pendingCount');
            
            count.textContent = pending.entries?.length || 0;

            if (!pending.entries || pending.entries.length === 0) {
                table.innerHTML = '<tr><td colspan="3" class="text-center">No pending voices</td></tr>';
                return;
            }

            table.innerHTML = pending.entries.map(entry => `
                <tr>
                    <td><code>${entry.id}</code></td>
                    <td>${new Date(entry.timestamp * 1000).toLocaleString()}</td>
                    <td>
                        <button class="btn btn-sm btn-play" onclick="playAudio('${entry.audio_url}')">
                            <i class="bi bi-play-fill"></i> Play
                        </button>
                        <button class="btn btn-sm btn-enroll" onclick="enrollPending('${entry.id}')">
                            <i class="bi bi-check-circle"></i> Enroll
                        </button>
                        <button class="btn btn-sm btn-reject" onclick="rejectPending('${entry.id}')">
                            <i class="bi bi-x-circle"></i> Reject
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        function updateBlocklist(enrolled) {
            const table = document.getElementById('blocklistTable');
            
            if (!enrolled || enrolled.length === 0) {
                table.innerHTML = '<tr><td colspan="4" class="text-center">No enrolled identities</td></tr>';
                return;
            }

            table.innerHTML = enrolled.map(person => {
                const statusBadge = person.blocked 
                    ? '<span class="badge badge-blocked">BLOCKED</span>'
                    : '<span class="badge badge-active">ACTIVE</span>';
                
                const typeBadge = person.is_virtual 
                    ? '<span class="badge badge-virtual">Virtual</span>'
                    : '<span class="badge bg-secondary">Enrolled</span>';

                return `
                    <tr ${person.is_virtual ? 'style="border-left: 4px solid #764ba2;"' : ''}>
                        <td><strong>${person.display_name}</strong></td>
                        <td>${statusBadge}</td>
                        <td>${person.sample_count}</td>
                        <td>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" 
                                       id="block_${person.person_id}" 
                                       ${person.blocked ? '' : 'checked'}
                                       onchange="toggleBlocklist('${person.person_id}')">
                                <label class="form-check-label" for="block_${person.person_id}">
                                    ${person.blocked ? 'Blocked' : 'Active'}
                                </label>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        function updateEnrolled(enrolled) {
            const table = document.getElementById('enrolledTable');
            const count = document.getElementById('enrolledCount');
            
            // Filter out virtual user for this table
            const realEnrolled = enrolled.filter(p => !p.is_virtual);
            count.textContent = realEnrolled.length;

            if (realEnrolled.length === 0) {
                table.innerHTML = '<tr><td colspan="5" class="text-center">No enrolled identities</td></tr>';
                return;
            }

            table.innerHTML = realEnrolled.map(person => {
                const statusBadge = person.blocked 
                    ? '<span class="badge badge-blocked">BLOCKED</span>'
                    : '<span class="badge badge-active">ACTIVE</span>';

                const hasOverride = person.threshold_override !== null && person.threshold_override !== undefined;
                const sliderVal = hasOverride ? person.threshold_override : 0.50;
                const valLabel = hasOverride
                    ? person.threshold_override.toFixed(2)
                    : '<span class="text-muted">global</span>';

                return `
                    <tr>
                        <td><strong>${person.display_name}</strong></td>
                        <td>${person.sample_count}</td>
                        <td><span class="badge bg-secondary">Enrolled</span></td>
                        <td>${statusBadge}</td>
                        <td>
                            <div class="d-flex align-items-center gap-2">
                                <input type="range" class="form-range threshold-slider" style="width:110px"
                                       min="0.10" max="0.90" step="0.01" value="${sliderVal}"
                                       id="pt_${person.person_id}"
                                       oninput="document.getElementById('ptv_${person.person_id}').textContent = parseFloat(this.value).toFixed(2)"
                                       onchange="setPersonThreshold('${person.person_id}', parseFloat(this.value))">
                                <span id="ptv_${person.person_id}" style="min-width:60px">${valLabel}</span>
                                <button class="btn btn-sm btn-outline-secondary"
                                        onclick="clearPersonThreshold('${person.person_id}')"
                                        title="Clear override (use global)">Clear</button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        async function setPersonThreshold(personId, threshold) {
            try {
                await fetch('/api/settings/person_threshold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ person_id: personId, threshold: threshold })
                });
            } catch (error) {
                console.error('Error setting person threshold:', error);
            }
        }

        async function clearPersonThreshold(personId) {
            try {
                await fetch('/api/settings/person_threshold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ person_id: personId, threshold: null })
                });
                loadState();
            } catch (error) {
                console.error('Error clearing person threshold:', error);
            }
        }

        function updateClusters(clusters) {
            const container = document.getElementById('clustersList');
            const count = document.getElementById('clusterCount');
            
            count.textContent = clusters.length || 0;

            if (!clusters || clusters.length === 0) {
                container.innerHTML = '<p class="text-center">No clusters available</p>';
                return;
            }

            container.innerHTML = clusters.map(cluster => `
                <div class="cluster-card">
                    <div class="row align-items-center">
                        <div class="col-md-8">
                            <strong>Cluster ${cluster.cluster_id}</strong> - 
                            ${cluster.stats.count} samples
                            <span class="badge similarity-badge ms-2">
                                Similarity: ${(cluster.stats.avg_similarity * 100).toFixed(1)}%
                            </span>
                            ${cluster.stats.time_range.start ? `
                                <div class="text-muted small mt-1">
                                    Time range: ${cluster.stats.time_range.start.split('T')[0]}
                                </div>
                            ` : ''}
                        </div>
                        <div class="col-md-4 text-end">
                            <button class="btn btn-sm btn-primary" onclick="viewClusterSamples(${cluster.cluster_id})">
                                <i class="bi bi-list-ul"></i> Samples
                            </button>
                            <button class="btn btn-sm btn-play" onclick="playCluster(${cluster.cluster_id})">
                                <i class="bi bi-play-fill"></i> Play All
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Event handlers
        document.getElementById('injectionToggle').addEventListener('change', async (e) => {
            try {
                await fetch('/api/settings/injection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: e.target.checked })
                });
            } catch (error) {
                console.error('Error updating injection:', error);
            }
        });

        document.getElementById('transcriptPreferredToggle').addEventListener('change', async (e) => {
            try {
                await fetch('/api/settings/transcript_preferred', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: e.target.checked })
                });
            } catch (error) {
                console.error('Error updating transcript preferred:', error);
            }
        });

        document.getElementById('thresholdSlider').addEventListener('input', (e) => {
            document.getElementById('thresholdValue').textContent = parseFloat(e.target.value).toFixed(2);
        });

        document.getElementById('thresholdSlider').addEventListener('change', async (e) => {
            try {
                await fetch('/api/settings/threshold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ threshold: parseFloat(e.target.value) })
                });
            } catch (error) {
                console.error('Error updating threshold:', error);
            }
        });

        async function toggleBlocklist(personId) {
            try {
                await fetch('/api/blocklist/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ person_id: personId })
                });
                loadState(); // Refresh
            } catch (error) {
                console.error('Error toggling blocklist:', error);
            }
        }

        function playAudio(url) {
            const audio = new Audio(url);
            audio.play();
        }

        async function enrollPending(pendingId) {
            const name = prompt('Enter person name (will be converted to person_id):');
            if (!name) return;

            try {
                const response = await fetch('/api/pending/enroll', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pending_id: pendingId,
                        display_name: name
                    })
                });
                
                if (response.ok) {
                    alert('Enrolled successfully!');
                    loadState();
                }
            } catch (error) {
                console.error('Error enrolling:', error);
                alert('Enrollment failed');
            }
        }

        async function rejectPending(pendingId) {
            if (!confirm('Reject this voice sample?')) return;

            try {
                await fetch('/api/pending/reject', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pending_id: pendingId })
                });
                loadState();
            } catch (error) {
                console.error('Error rejecting:', error);
            }
        }

        function viewClusterSamples(clusterId) {
            alert(`Cluster ${clusterId} sample viewer - Coming soon!`);
        }

        function playCluster(clusterId) {
            alert(`Play all samples from cluster ${clusterId} - Coming soon!`);
        }

        // === Thing Engine Functions ===
        
        async function loadThingEngine() {
            try {
                const response = await fetch('/api/enrolled');
                const people = await response.json();
                const table = document.getElementById('thingEngineTable');
                
                // Filter out virtual "user"
                const enrolled = people.filter(p => !p.is_virtual);
                
                if (enrolled.length === 0) {
                    table.innerHTML = '<tr><td colspan="4" class="text-center">No enrolled identities</td></tr>';
                    return;
                }
                
                table.innerHTML = enrolled.map(person => `
                    <tr>
                        <td>${person.display_name}</td>
                        <td>
                            <div class="input-group input-group-sm">
                                <input type="text" class="form-control" id="transform_${person.person_id}" 
                                       placeholder="New name..." style="max-width: 200px;">
                                <button class="btn btn-sm btn-primary" onclick="transformIdentity('${person.person_id}')">
                                    <i class="bi bi-arrow-repeat"></i> Rename
                                </button>
                            </div>
                        </td>
                        <td>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="merge_${person.person_id}"
                                       onchange="updateMergeButton()">
                            </div>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-danger" onclick="deleteIdentity('${person.person_id}')">
                                <i class="bi bi-trash"></i> Delete
                            </button>
                        </td>
                    </tr>
                `).join('');
                
                updateMergeButton();
            } catch (error) {
                console.error('Error loading Thing Engine:', error);
            }
        }
        
        async function transformIdentity(personId) {
            const input = document.getElementById(`transform_${personId}`);
            const newName = input.value.trim();
            
            if (!newName) {
                alert('Please enter a new name');
                return;
            }
            
            if (!confirm(`Rename this identity to "${newName}"?`)) return;
            
            try {
                const response = await fetch('/api/thing_engine/transform', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        person_id: personId,
                        new_name: newName
                    })
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    alert('Transform queued successfully!');
                    input.value = '';
                    setTimeout(loadState, 3000); // Reload after 3 seconds
                } else {
                    alert('Transform failed: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error transforming:', error);
                alert('Transform failed');
            }
        }
        
        async function deleteIdentity(personId) {
            if (!confirm(`PERMANENTLY DELETE this identity? This cannot be undone!`)) return;
            if (!confirm('Are you ABSOLUTELY SURE? All voice samples will be deleted!')) return;
            
            try {
                const response = await fetch('/api/thing_engine/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ person_id: personId })
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    alert('Delete queued successfully!');
                    setTimeout(loadState, 3000); // Reload after 3 seconds
                } else {
                    alert('Delete failed: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error deleting:', error);
                alert('Delete failed');
            }
        }
        
        function updateMergeButton() {
            const checkboxes = document.querySelectorAll('[id^="merge_"]');
            const checked = Array.from(checkboxes).filter(cb => cb.checked);
            const btn = document.getElementById('executeMergeBtn');
            
            btn.disabled = checked.length < 2;
            btn.textContent = checked.length >= 2 
                ? `Merge ${checked.length} Tagged Identities`
                : 'Merge Tagged Identities (select 2+)';
        }
        
        async function executeMerge() {
            const checkboxes = document.querySelectorAll('[id^="merge_"]');
            const tagged = Array.from(checkboxes)
                .filter(cb => cb.checked)
                .map(cb => cb.id.replace('merge_', ''));
            
            if (tagged.length < 2) {
                alert('Please tag at least 2 identities to merge');
                return;
            }
            
            const newName = prompt('Enter name for merged identity:');
            if (!newName || !newName.trim()) return;
            
            if (!confirm(`Merge ${tagged.length} identities into "${newName}"?`)) return;
            
            try {
                const response = await fetch('/api/thing_engine/merge', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_ids: tagged,
                        new_name: newName.trim()
                    })
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    alert('Merge queued successfully!');
                    setTimeout(loadState, 5000); // Reload after 5 seconds
                } else {
                    alert('Merge failed: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error merging:', error);
                alert('Merge failed');
            }
        }
        
        // Wire up merge button
        document.addEventListener('DOMContentLoaded', function() {
            const mergeBtn = document.getElementById('executeMergeBtn');
            if (mergeBtn) {
                mergeBtn.addEventListener('click', executeMerge);
            }
        });

        // Auto-refresh
        setInterval(loadState, 2000);
        loadState();
    </script>
</body>
</html>
'''


# === State File Helpers ===

def load_json(filepath: str, default: dict) -> dict:
    """Load JSON file with fallback to default"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
    return default


def save_json(filepath: str, data: dict):
    """Save JSON file atomically"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, filepath)


def get_settings() -> dict:
    """Load settings, with switch states sourced from config.json (single source
    of truth) and the active threshold read live from thresholds.json (the file
    the analyzer reads). This keeps the dashboard's display truthful even with no
    broker — it never relies on the MQTT-driven settings.json mirror."""
    settings = load_json(SETTINGS_FILE, {
        'inject_identity': True,
        'active_threshold': 0.50
    })
    # config.json is authoritative for the two switches; overlay it.
    settings['inject_identity'] = get_inject_identity()
    settings['transcript_preferred'] = get_transcript_preferred()
    # thresholds.json is authoritative for the active match threshold.
    try:
        with open(THRESHOLD_FILE, 'r') as f:
            thr = json.load(f)
        settings['active_threshold'] = float(thr.get('MATCH_T_ACTIVE', settings.get('active_threshold', 0.50)))
    except Exception:
        pass
    return settings


def get_active_state() -> dict:
    """Load active_state.json"""
    return load_json(ACTIVE_STATE_FILE, {})


def get_pending() -> dict:
    """Load pending.json. The publisher writes it as a raw list (the pending
    buffer); the UI expects {'entries': [...]}. Normalize both shapes."""
    data = load_json(PENDING_FILE, [])
    if isinstance(data, list):
        return {'entries': data}
    if isinstance(data, dict):
        # already wrapped, or wrap a stray dict defensively
        return data if 'entries' in data else {'entries': []}
    return {'entries': []}


def get_clusters() -> list:
    """Load clusters.json"""
    data = load_json(CLUSTERS_FILE, [])
    return data if isinstance(data, list) else []


def get_enrolled_people() -> list:
    """Get all enrolled people including virtual 'user'"""
    people = []
    
    # Add virtual "user" first
    user_settings = load_json(USER_SETTINGS_FILE, {'blocked': False})
    people.append({
        'person_id': 'user',
        'display_name': 'user',
        'sample_count': 0,
        'blocked': user_settings.get('blocked', False),
        'is_virtual': True
    })
    
    # Add enrolled people
    if not os.path.exists(ENROLL_DIR):
        return people
    
    for person_dir in Path(ENROLL_DIR).iterdir():
        if not person_dir.is_dir():
            continue
        
        person_id = person_dir.name
        metadata_file = person_dir / 'metadata.json'
        
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    display_name = metadata.get('display_name', person_id.replace('_', ' ').title())
                    sample_count = len(metadata.get('samples', []))
                    blocked = metadata.get('blocked', False)
            except:
                display_name = person_id.replace('_', ' ').title()
                sample_count = 0
                blocked = False
        else:
            display_name = person_id.replace('_', ' ').title()
            sample_count = 0
            blocked = False
        
        people.append({
            'person_id': person_id,
            'display_name': display_name,
            'sample_count': sample_count,
            'blocked': blocked,
            'is_virtual': False
        })

    # Attach current per-person threshold overrides (from thresholds.json), so
    # the dashboard can display/edit them. None = no override (uses global).
    overrides = get_person_overrides()
    for p in people:
        val = overrides.get(p['person_id'])
        try:
            p['threshold_override'] = float(val) if val is not None else None
        except (TypeError, ValueError):
            p['threshold_override'] = None

    # Sort: virtual user first, then by sample count descending
    return sorted(people, key=lambda x: (not x['is_virtual'], -x['sample_count']))


def get_person_overrides() -> dict:
    """Read the PERSON_OVERRIDES map from thresholds.json (the dashboard/analyzer
    shared file). Returns {person_id: threshold}; empty on any error."""
    try:
        with open(THRESHOLD_FILE, 'r') as f:
            data = json.load(f)
        ov = data.get('PERSON_OVERRIDES', {})
        return ov if isinstance(ov, dict) else {}
    except Exception:
        return {}


# === API Routes ===

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/state/settings')
def api_settings():
    """Get current settings"""
    return jsonify(get_settings())


@app.route('/api/state/active')
def api_active_state():
    """Get current active state"""
    return jsonify(get_active_state())


@app.route('/api/state/pending')
def api_pending():
    """Get pending voices"""
    return jsonify(get_pending())


@app.route('/api/state/clusters')
def api_clusters():
    """Get voice clusters"""
    return jsonify(get_clusters())


@app.route('/api/enrolled')
def api_enrolled():
    """Get enrolled people"""
    return jsonify(get_enrolled_people())


@app.route('/api/settings/injection', methods=['POST'])
def update_injection():
    """Update ID injection setting. config.json is the source of truth; echo retained MQTT for HA."""
    data = request.get_json()
    enabled = bool(data.get('enabled', False))
    update_voicebm_config_key('inject_identity', enabled)
    publish_retained('voicebm/inject_identity', 'ON' if enabled else 'OFF')
    return jsonify({'success': True})


@app.route('/api/settings/transcript_preferred', methods=['POST'])
def update_transcript_preferred():
    """Update Transcript Preferred setting. config.json is the source of truth; echo retained MQTT for HA."""
    data = request.get_json()
    enabled = bool(data.get('enabled', False))
    update_voicebm_config_key('transcript_preferred', enabled)
    publish_retained('voicebm/transcript_preferred', 'ON' if enabled else 'OFF')
    return jsonify({'success': True})


@app.route('/api/settings/person_threshold', methods=['POST'])
def update_person_threshold():
    """Set or clear a per-person threshold override by writing the
    PERSON_OVERRIDES map in thresholds.json — the same file the analyzer reads.
    No MQTT, so it works with no broker. Send {"person_id": "...", "threshold": x}
    to set, or {"person_id": "...", "threshold": null} to clear the override."""
    data = request.get_json()
    person_id = data.get('person_id')
    if not person_id:
        return jsonify({'error': 'Missing person_id'}), 400

    raw = data.get('threshold', None)
    clearing = raw is None
    if not clearing:
        try:
            threshold = float(raw)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid threshold'}), 400
        if not (0.10 <= threshold <= 0.90):
            return jsonify({'error': 'Threshold out of range (0.10-0.90)'}), 400

    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, 'r') as f:
                tdata = json.load(f)
        else:
            tdata = {}
    except Exception:
        tdata = {}
    overrides = tdata.get('PERSON_OVERRIDES', {})
    if not isinstance(overrides, dict):
        overrides = {}
    if clearing:
        overrides.pop(person_id, None)
    else:
        overrides[person_id] = threshold
    tdata['PERSON_OVERRIDES'] = overrides

    try:
        os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".thresholds.", suffix=".tmp",
                                        dir=os.path.dirname(THRESHOLD_FILE))
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(tdata, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, THRESHOLD_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        return jsonify({'error': f'Failed to write person threshold: {e}'}), 500

    return jsonify({'success': True, 'cleared': clearing})


@app.route('/api/settings/threshold', methods=['POST'])
def update_threshold():
    """Update the active match threshold by writing MATCH_T_ACTIVE directly to
    thresholds.json — the file the analyzer reads live on every request. The
    dashboard does NOT use MQTT (so it works for users with no broker, e.g.
    OpenWebUI-only setups); it reaches the same file the HA MQTT path ultimately
    writes. Read-modify-write preserving other keys (e.g. GALLERY_MAX)."""
    data = request.get_json()
    try:
        threshold = float(data.get('threshold', 0.50))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid threshold'}), 400
    if not (0.01 <= threshold <= 1.00):
        return jsonify({'error': 'Threshold out of range (0.01-1.00)'}), 400

    try:
        if os.path.exists(THRESHOLD_FILE):
            with open(THRESHOLD_FILE, 'r') as f:
                thresholds = json.load(f)
        else:
            thresholds = {}
    except Exception:
        thresholds = {}
    thresholds['MATCH_T_ACTIVE'] = threshold

    try:
        os.makedirs(os.path.dirname(THRESHOLD_FILE), exist_ok=True)
        # Atomic write so a concurrent analyzer read never sees a half-written file.
        fd, tmp_path = tempfile.mkstemp(prefix=".thresholds.", suffix=".tmp",
                                        dir=os.path.dirname(THRESHOLD_FILE))
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(thresholds, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, THRESHOLD_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        return jsonify({'error': f'Failed to write threshold: {e}'}), 500

    return jsonify({'success': True})


@app.route('/api/blocklist/toggle', methods=['POST'])
def toggle_blocklist():
    """Toggle blocklist for a person or virtual user"""
    data = request.get_json()
    person_id = data.get('person_id')
    
    if not person_id:
        return jsonify({'error': 'Missing person_id'}), 400
    
    # Special handling for virtual "user"
    if person_id == 'user':
        user_settings = load_json(USER_SETTINGS_FILE, {'blocked': False})
        user_settings['blocked'] = not user_settings.get('blocked', False)
        user_settings['last_updated'] = datetime.datetime.now().isoformat()
        save_json(USER_SETTINGS_FILE, user_settings)
        return jsonify({'success': True, 'blocked': user_settings['blocked']})
    
    # Handle enrolled person
    metadata_file = Path(ENROLL_DIR) / person_id / 'metadata.json'
    
    if not metadata_file.exists():
        return jsonify({'error': 'Person not found'}), 404
    
    metadata = load_json(str(metadata_file), {})
    metadata['blocked'] = not metadata.get('blocked', False)
    metadata['last_updated'] = datetime.datetime.now().isoformat()
    save_json(str(metadata_file), metadata)
    
    return jsonify({'success': True, 'blocked': metadata['blocked']})


@app.route('/api/pending/enroll', methods=['POST'])
def enroll_pending():
    """Enroll a pending voice by publishing to the existing pending_active/enroll
    MQTT topic. The global publisher's handle_pending_enroll does the actual file
    moves + metadata; the enrollment_watcher then publishes the HA device."""
    data = request.get_json()
    pending_id = data.get('pending_id')
    display_name = data.get('display_name', '').strip()

    if not pending_id or not display_name:
        return jsonify({'error': 'Missing required fields'}), 400

    person_id = display_name.lower().replace(' ', '_')

    # Payload shape required by handle_pending_enroll: id, person_id, display_name
    payload = json.dumps({
        "id": pending_id,
        "person_id": person_id,
        "display_name": display_name,
    })
    publish_command('voicebm/pending_active/enroll', payload)

    return jsonify({'success': True, 'person_id': person_id})


@app.route('/api/pending/reject', methods=['POST'])
def reject_pending():
    """Reject a pending voice by publishing to the existing pending_active/reject
    MQTT topic. The global publisher removes the pending files."""
    data = request.get_json()
    pending_id = data.get('pending_id')

    if not pending_id:
        return jsonify({'error': 'Missing pending_id'}), 400

    payload = json.dumps({"id": pending_id})
    publish_command('voicebm/pending_active/reject', payload)

    return jsonify({'success': True})


# === Thing Engine API Routes ===

def get_thing_engine_commands() -> dict:
    """Load Thing Engine command queue"""
    return load_json(THING_ENGINE_COMMANDS_FILE, {'commands': []})


def save_thing_engine_commands(data: dict):
    """Save Thing Engine command queue"""
    save_json(THING_ENGINE_COMMANDS_FILE, data)


def queue_thing_engine_command(command_type: str, **kwargs) -> str:
    """Queue a Thing Engine command and return command ID"""
    import uuid
    
    commands_data = get_thing_engine_commands()
    
    command_id = f"cmd_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
    
    command = {
        'id': command_id,
        'type': command_type,
        'status': 'pending',
        'timestamp': datetime.datetime.now().isoformat(),
        **kwargs
    }
    
    commands_data['commands'].append(command)
    save_thing_engine_commands(commands_data)
    
    return command_id


@app.route('/api/thing_engine/transform', methods=['POST'])
def thing_engine_transform():
    """Queue a transform (rename) operation"""
    data = request.get_json()
    person_id = data.get('person_id')
    new_name = data.get('new_name', '').strip()
    
    if not person_id or not new_name:
        return jsonify({'error': 'Missing person_id or new_name'}), 400
    
    # Verify person exists
    person_dir = Path(ENROLL_DIR) / person_id
    if not person_dir.exists():
        return jsonify({'error': 'Person not found'}), 404
    
    # Queue command
    command_id = queue_thing_engine_command(
        'transform',
        person_id=person_id,
        new_name=new_name
    )
    
    return jsonify({'success': True, 'command_id': command_id})


@app.route('/api/thing_engine/delete', methods=['POST'])
def thing_engine_delete():
    """Queue a delete operation"""
    data = request.get_json()
    person_id = data.get('person_id')
    
    if not person_id:
        return jsonify({'error': 'Missing person_id'}), 400
    
    # Verify person exists
    person_dir = Path(ENROLL_DIR) / person_id
    if not person_dir.exists():
        return jsonify({'error': 'Person not found'}), 404
    
    # Queue command
    command_id = queue_thing_engine_command(
        'delete',
        person_id=person_id
    )
    
    return jsonify({'success': True, 'command_id': command_id})


@app.route('/api/thing_engine/merge', methods=['POST'])
def thing_engine_merge():
    """Queue a merge operation"""
    data = request.get_json()
    source_ids = data.get('source_ids', [])
    new_name = data.get('new_name', '').strip()
    
    if len(source_ids) < 2:
        return jsonify({'error': 'At least 2 source identities required'}), 400
    
    if not new_name:
        return jsonify({'error': 'Missing new_name'}), 400
    
    # Verify all sources exist
    for source_id in source_ids:
        person_dir = Path(ENROLL_DIR) / source_id
        if not person_dir.exists():
            return jsonify({'error': f'Source identity not found: {source_id}'}), 404
    
    # Queue command
    command_id = queue_thing_engine_command(
        'merge',
        source_ids=source_ids,
        new_name=new_name
    )
    
    return jsonify({'success': True, 'command_id': command_id})


if __name__ == '__main__':
    print("=" * 60)
    print("VoiceBM Dashboard - LLM Voice Biometrics")
    print("by David M. Dryver Sr.")
    print("=" * 60)
    print(f"Dashboard URL: http://127.0.0.1:5000")
    print(f"Settings file: {SETTINGS_FILE}")
    print(f"Active state: {ACTIVE_STATE_FILE}")
    print(f"Pending: {PENDING_FILE}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
