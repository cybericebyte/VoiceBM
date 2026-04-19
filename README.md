# VoiceBM

"Voice BM is not a replacement for anything. It is an enhancement to fill a hole that exists within the local smart AI consumer communities. I built it and shared it so you didn't have to."

VoiceBM is a voice biometrics engine for Home Assistant. It identifies who is speaking, publishes identity signals via MQTT, and supports enrollment + blocklisting workflows.

> Scope note: VoiceBM is an engine. It exposes identity and controls; your UI/LLM/frontend decides how to use them.

## What it does
- Creates speaker embeddings and matches against an enrolled gallery
- Falls back to a virtual **user** identity for unknown speakers
- Publishes identity + status topics over MQTT (Home Assistant discovery-friendly)
- Per-identity blocklist switches (including **user**) to fail STT silently when blocked
- Room-aware collection, roomless identity (identity is global)

## What it does NOT do
- It’s not a full conversational UX
- It does not decide “what to say” or how to build assistants
- It doesn’t assume a specific frontend (Home Assistant, OpenWebUI, local LLM, etc.)



Here A commented example yaml of how you can use VoiceBM:

```yaml
alias: "VoiceBM: Master Conversation Flow with RAG"
description: "Example automation demonstrating VoiceBM identity primitives with profile injection, RAG context enrichment, and web search fallback"
triggers:
  # Trigger when a new user request arrives.
  # The sensor voicebm_user_full_request normally holds the idle placeholder "..."
  # This automation fires only on the transition from "..." to a real request.
  - trigger: state
    entity_id:
      - sensor.voicebm_user_full_request
    from:
      - ...
conditions:
  # Validate that the message contains actual content (not idle/placeholder)
  # Splits at the first colon to separate speaker tag from message text.
  - condition: template
    value_template: >
      {% set raw = states('sensor.voicebm_user_full_request') %}
      {% if ':' in raw %}
        {% set message = raw.split(':', 1)[1].lstrip() %}
      {% else %}
        {% set message = raw %}
      {% endif %}
      {{ message | trim not in ('', '...', 'Ellipsis', 'unknown') }}
actions:
  # --- VARIABLES: Extract and prepare request context ---
  - variables:
      # Raw user message (without speaker prefix)
      raw_text: >
        {% set v = states('sensor.voicebm_user_full_request') %}
        {{ (v.split(':', 1)[1] if ':' in v else v) | trim }}
      # VoiceBM primitive: active speaker identity (unique ID slug)
      speaker_id: "{{ states('sensor.voicebm_active_speaker_id') }}"
      # VoiceBM primitive: active speaker display name (e.g., "David Dryver Sr")
      speaker_display: "{{ states('sensor.voicebm_active_speaker_display') }}"
      # Use speaker_id as the person identifier throughout the automation
      person_id: "{{ speaker_id }}"
      # VoiceBM primitive: per-person profile device (MQTT sensor)
      profile_entity: sensor.{{ person_id }}_personal_profile
      # VoiceBM primitive: blocked status from profile attributes
      is_blocked: >
        {{ state_attr(profile_entity, 'blocked') | default(false, true) | bool }}
      # Build a tag for the final prompt (e.g., "David Dryver Sr: ")
      message_tag: >
        {% if speaker_id == 'user' %}user {% else %}{{ speaker_display }} {% endif %}
      # Final prompt string sent to the assistant
      assistant_prompt: "{{ message_tag }}: {{ raw_text }}"

  # --- GUARD 1: No valid speaker identified ---
  # If speaker_id is empty, clean up all state and stop.
  - if:
      - condition: template
        value_template: "{{ speaker_id | trim == '' }}"
    then:
      - action: switch.turn_off
        target:
          entity_id: switch.assistant_thinking_context_processing
        continue_on_error: true
      # Reset MQTT request/response topics to idle placeholder
      - action: mqtt.publish
        data:
          topic: andrea/user/full
          payload: ...
          retain: true
      - action: mqtt.publish
        data:
          topic: andrea/response/full
          payload: ...
          retain: true
      # Turn off any active voice session
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/voice"
          payload: "OFF"
          retain: true
      - action: mqtt.publish
        data:
          topic: user/voice
          payload: "OFF"
          retain: true
      # Clear RAG readiness flag
      - action: input_text.set_value
        target:
          entity_id: input_text.rag_ready
        data:
          value: ""
      # Clear RAG context state
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/rag/context/state"
          payload: empty
          retain: true
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/rag/context/attributes"
          payload: |
            {"status": "empty", "person_id": "{{ person_id }}",
             "chunks": {}, "keys_returned": [], "token_estimate": 0}
          retain: true
      # Wait for any ongoing TTS to finish (up to 30 seconds)
      - if:
          - condition: state
            entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
            state: "on"
        then:
          - wait_for_trigger:
              - trigger: state
                entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
                to: "off"
            continue_on_timeout: true
            timeout:
              seconds: 30
      # Clear voice biometric identity
      - action: mqtt.publish
        data:
          topic: voicebm/active/identity
          payload: >-
            {"speaker_id": "", "display_name": "", "confidence": 0, "decision": "", "score": 0}
          retain: true
      - action: mqtt.publish
        data:
          topic: voicebiometrics/active_speaker
          payload: none
          retain: true
      - stop: "Stopping automation: speaker_id is blank"

  # --- GUARD 2: Speaker is blocked ---
  # If the speaker is blocked, clean up state and stop.
  - if:
      - condition: template
        value_template: "{{ is_blocked }}"
    then:
      - action: switch.turn_off
        target:
          entity_id: switch.assistant_thinking_context_processing
        continue_on_error: true
      - action: mqtt.publish
        data:
          topic: andrea/user/full
          payload: ...
          retain: true
      - action: mqtt.publish
        data:
          topic: andrea/response/full
          payload: ...
          retain: true
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/voice"
          payload: "OFF"
          retain: true
      - action: mqtt.publish
        data:
          topic: user/voice
          payload: "OFF"
          retain: true
      - action: input_text.set_value
        target:
          entity_id: input_text.rag_ready
        data:
          value: ""
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/rag/context/state"
          payload: empty
          retain: true
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/rag/context/attributes"
          payload: |
            {"status": "empty", "person_id": "{{ person_id }}",
             "chunks": {}, "keys_returned": [], "token_estimate": 0}
          retain: true
      - if:
          - condition: state
            entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
            state: "on"
        then:
          - wait_for_trigger:
              - trigger: state
                entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
                to: "off"
            continue_on_timeout: true
            timeout:
              seconds: 30
      - action: mqtt.publish
        data:
          topic: voicebm/active/identity
          payload: >-
            {"speaker_id": "", "display_name": "", "confidence": 0, "decision": "", "score": 0}
          retain: true
      - action: mqtt.publish
        data:
          topic: voicebiometrics/active_speaker
          payload: none
          retain: true
      - stop: "Stopping automation: speaker_id is blocked"
    continue_on_error: true

  # --- PROFILE EXISTENCE CHECK ---
  # Ensure a profile sensor exists for this speaker.
  # If not, create it via MQTT discovery with default attributes.
  - variables:
      has_profile: >
        {{ states(profile_entity) is not none and states(profile_entity) != 'None' }}
  - if:
      - condition: template
        value_template: "{{ not has_profile }}"
    then:
      - action: mqtt.publish
        data:
          topic: homeassistant/sensor/{{ person_id }}_personal_profile/config
          payload: |
            {"name": "{{ person_id }} Personal Profile",
             "state_topic": "{{ person_id }}/personal_profile/state",
             "json_attributes_topic": "{{ person_id }}/personal_profile/attributes",
             "device": {"identifiers": ["{{ person_id }}_profile"], "name": "{{ person_id }}"}}
          retain: true
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/personal_profile/state"
          payload: active
          retain: true
      - action: mqtt.publish
        data:
          topic: "{{ person_id }}/personal_profile/attributes"
          payload: |
            {"household_role": "none", "age": "", "birthdate": "",
             "nickname": "{{ person_id }}", "preferred_name": "unknown",
             "address_style": "", "relationship_to_owner": "unknown",
             "music_preference": "", "hobbies": "", "interests": "",
             "projects": "", "coffee_preference": "", "media": "",
             "favorite_color": "", "light_preference": "", "temp_comfort": "",
             "permissions": "", "security_tier": "", "personal_context": "",
             "profession": "", "employment": "", "medical": "",
             "presence": "", "emergency_contact": "", "language_preference": "",
             "dietary_restrictions": "", "vehicle": "", "typical_schedule": "",
             "communication_style": "", "known_devices": "", "blocked": false}
          retain: true

  # --- THINKING SWITCH SYNCHRONIZATION (disabled, but kept for reference) ---
  # The thinking switch is automatically turned on by a separate automation
  # when conversation.process fires. We ensure it's off before proceeding.
  - action: switch.turn_off
    metadata: {}
    target:
      entity_id: switch.assistant_thinking_context_processing
    data: {}
    enabled: false
  - if:
      - condition: state
        entity_id: switch.assistant_thinking_context_processing
        state: "on"
    then:
      - wait_for_trigger:
          - trigger: state
            entity_id: switch.assistant_thinking_context_processing
            to: "off"

  # --- PRIME ASSISTANT WITH SPEAKER'S PROFILE ---
  # Send the speaker's personal profile attributes as a system message.
  # This gives the assistant context about who is talking.
  - action: conversation.process
    data:
      text: >
        <system:> ({{ states('sensor.voicebm_active_speaker_display') }}:
        preferred_name: {{ state_attr(profile_entity, 'preferred_name') or person_id }}:
        household_role: {{ state_attr(profile_entity, 'household_role') or '' }}
        age: {{ state_attr(profile_entity, 'age') or '' }}
        birthdate: {{ state_attr(profile_entity, 'birthdate') or '' }}
        nickname: {{ state_attr(profile_entity, 'nickname') or '' }}
        address_style: {{ state_attr(profile_entity, 'address_style') or '' }}
        relationship_to_owner: {{ state_attr(profile_entity, 'relationship_to_owner') or '' }}
        music_preference: {{ state_attr(profile_entity, 'music_preference') or '' }}
        hobbies: {{ state_attr(profile_entity, 'hobbies') or '' }}
        interests: {{ state_attr(profile_entity, 'interests') or '' }}
        projects: {{ state_attr(profile_entity, 'projects') or '' }}
        coffee_preference: {{ state_attr(profile_entity, 'coffee_preference') or '' }}
        media: {{ state_attr(profile_entity, 'media') or '' }}
        favorite_color: {{ state_attr(profile_entity, 'favorite_color') or '' }}
        light_preference: {{ state_attr(profile_entity, 'light_preference') or '' }}
        temp_comfort: {{ state_attr(profile_entity, 'temp_comfort') or '' }}
        permissions: {{ state_attr(profile_entity, 'permissions') or '' }}
        security_tier: {{ state_attr(profile_entity, 'security_tier') or '' }}
        personal_context: {{ state_attr(profile_entity, 'personal_context') or '' }}
        profession: {{ state_attr(profile_entity, 'profession') or '' }}
        employment: {{ state_attr(profile_entity, 'employment') or '' }}
        medical: {{ state_attr(profile_entity, 'medical') or '' }}
        presence: {{ state_attr(profile_entity, 'presence') or '' }}
        emergency_contact: {{ state_attr(profile_entity, 'emergency_contact') or '' }}
        language_preference: {{ state_attr(profile_entity, 'language_preference') or '' }}
        dietary_restrictions: {{ state_attr(profile_entity, 'dietary_restrictions') or '' }}
        vehicle: {{ state_attr(profile_entity, 'vehicle') or '' }}
        typical_schedule: {{ state_attr(profile_entity, 'typical_schedule') or '' }}
        communication_style: {{ state_attr(profile_entity, 'communication_style') or '' }}
        known_devices: {{ state_attr(profile_entity, 'known_devices') or '' }}
        relationships: {{ state_attr(profile_entity, 'relationships') or '' }})
      agent_id: conversation.assistant
      conversation_id: assistant_master_context

  # --- THINKING SWITCH SYNCHRONIZATION (again, disabled) ---
  - action: switch.turn_off
    metadata: {}
    target:
      entity_id: switch.assistant_thinking_context_processing
    data: {}
    enabled: false

  # --- RAG CONTEXT ENRICHMENT (only for known speakers, not generic 'user') ---
  - if:
      - condition: template
        value_template: "{{ person_id != 'user' }}"
    then:
      # Determine if RAG context is needed by checking if any word from the query
      # matches keywords in the speaker's projects, hobbies, interests, or personal_context.
      - variables:
          needs_rag: >
            {% set query_lower = raw_text | lower %}
            {% set query_words = query_lower.split() %}
            {% set matches = namespace(found=false) %}
            {% for key in ['projects', 'hobbies', 'interests', 'personal_context'] %}
              {% set val = state_attr(profile_entity, key) or '' %}
              {% if val | trim != '' %}
                {% set val_lower = val | lower %}
                {% for word in query_words %}
                  {% set clean_word = word | regex_replace('[^a-z0-9]', '') %}
                  {% if clean_word | length > 3 and clean_word in val_lower %}
                    {% set matches.found = true %}
                  {% endif %}
                {% endfor %}
              {% endif %}
            {% endfor %}
            {{ matches.found }}
      - if:
          - condition: template
            value_template: "{{ needs_rag }}"
        then:
          # Clear any stale RAG attributes before querying
          - action: mqtt.publish
            data:
              topic: "{{ person_id }}/rag/context/attributes"
              payload: |
                {"status": "empty", "person_id": "{{ person_id }}",
                 "chunks": {}, "keys_returned": [], "token_estimate": 0}
              retain: true
          # Publish a RAG query request. External service processes this and
          # sets input_text.rag_ready to "ready" when complete.
          - action: mqtt.publish
            data:
              topic: "{{ person_id }}/rag/query"
              payload: |
                {
                  "person_id": "{{ person_id }}",
                  "query_text": {{ raw_text | to_json }},
                  "always_keys": ["medical", "dietary_restrictions", "emergency_contact"],
                  "semantic_keys": ["projects", "personal_context", "hobbies", "interests"]
                }
          # Wait up to 10 seconds for the RAG service to signal readiness.
          - if:
              - condition: not
                conditions:
                  - condition: state
                    entity_id: input_text.rag_ready
                    state: ready
            then:
              - wait_for_trigger:
                  - trigger: state
                    entity_id: input_text.rag_ready
                    to: ready
                timeout: "00:00:10"
                continue_on_timeout: true
      # Retrieve the RAG context chunks from the per‑speaker RAG context sensor.
      - variables:
          rag_chunks: |
            {% if needs_rag %}
              {% set rag = state_attr('sensor.' ~ person_id ~ '_rag_context', 'chunks') %}
              {{ rag if rag is not none else {} }}
            {% else %}
              {}
            {% endif %}
          rag_detail_block: |
            {% if needs_rag %}
              {% set ns = namespace(lines=[]) %}
              {% for key, val in rag_chunks.items() %}
                {% if val | trim != '' %}
                  {% set ns.lines = ns.lines + [val] %}
                {% endif %}
              {% endfor %}
              {{ ns.lines | join('\n\n') }}
            {% else %}
              
            {% endif %}
      # If we have any RAG content, inject it as a system message.
      - if:
          - condition: template
            value_template: "{{ rag_detail_block | trim != '' }}"
        then:
          - if:
              - condition: state
                entity_id: switch.assistant_thinking_context_processing
                state: "on"
            then:
              - wait_for_trigger:
                  - trigger: state
                    entity_id: switch.assistant_thinking_context_processing
                    to: "off"
          - action: conversation.process
            data:
              text: "{{ rag_detail_block }}"
              agent_id: conversation.assistant
              conversation_id: assistant_master_context
          - action: switch.turn_off
            target:
              entity_id: switch.assistant_thinking_context_processing

  # --- INTERNET SEARCH HANDLING (disabled delay) ---
  - delay:
      seconds: 1
    enabled: false
  - if:
      - condition: state
        entity_id: switch.internet_search_in_progress
        state: "on"
    then:
      - wait_for_trigger:
          - trigger: state
            entity_id: switch.internet_search_in_progress
            from: "on"
            to: "off"
      - delay:
          seconds: 1
    enabled: false

  # --- USER-INITIATED WEB SEARCH ---
  # If the user's query contains search keywords, perform a web search.
  - if:
      - condition: template
        value_template: |-
          {% set q = raw_text | lower %}
          {{ 'search' in q or 'look up' in q or 'find out' in q
             or 'who is' in q or 'what is' in q or 'web' in q }}
    then:
      # Wait for thinking switch to be off before generating the "searching" response.
      - if:
          - condition: state
            entity_id: switch.assistant_thinking_context_processing
            state: "on"
        then:
          - wait_for_trigger:
              - trigger: state
                entity_id: switch.assistant_thinking_context_processing
                to: "off"
      # Ask the assistant to state that it's searching.
      - action: conversation.process
        data:
          text: >-
            <system:> in your own words state you need a moment to lookup the
            information online.((keep it Short 1 or 2 sentences MAX.)
          agent_id: conversation.assistant
          conversation_id: assistant_master_context
        response_variable: assistant_response_searching
      - action: switch.turn_off
        target:
          entity_id: switch.assistant_thinking_context_processing
      # Speak the "searching" message.
      - action: tts.speak
        target:
          entity_id: tts.openai_tts_assistant_chatterbox
        data:
          media_player_entity_id: >-
            media_player.{{
            states('sensor.satellite_origin_bus_satellite_origin') |
            replace('assist_satellite.', '') }}_media_player
          message: "{{ assistant_response_searching.response.speech.plain.speech }}"
      # Wait for thinking switch again.
      - if:
          - condition: state
            entity_id: switch.assistant_thinking_context_processing
            state: "on"
        then:
          - wait_for_trigger:
              - trigger: state
                entity_id: switch.assistant_thinking_context_processing
                to: "off"
      # Extract search intent using a dedicated extraction agent.
      - action: conversation.process
        data:
          text: >-
            Extract the search intent from the following text into a clean query
            string. Output ONLY valid JSON in this exact format: {"query": "the
            search terms"}. If no search is detected, return {"query": "none"}.
            Text to analyze: {{ raw_text | to_json }}
          agent_id: conversation.assistant_net_hands
        response_variable: gemma_extraction
      - action: switch.turn_off
        target:
          entity_id: switch.assistant_thinking_context_processing
      # Parse the JSON response.
      - variables:
          search_intent: >-
            {% set raw = gemma_extraction.response.speech.plain.speech %}
            {% set clean = raw | replace('```json', '') | replace('```', '') | trim %}
            {{ (clean | from_json).query }}
      # Only proceed if a valid search query was extracted.
      - condition: template
        value_template: "{{ search_intent != 'none' }}"
      # Call the SearXNG REST command.
      - action: rest_command.assistant_search_searxng
        data:
          search_query: "{{ search_intent }}"
        response_variable: searxng_response
      # Package the search results into a JSON receipt.
      - variables:
          search_receipt: |-
            {{
              {
                "query": searxng_response.content.query | default(search_intent, true),
                "number_of_results": searxng_response.content.number_of_results | default(none),
                "results": searxng_response.content.results | default([], true),
                "answers": searxng_response.content.answers | default([], true),
                "corrections": searxng_response.content.corrections | default([], true),
                "infoboxes": searxng_response.content.infoboxes | default([], true),
                "suggestions": searxng_response.content.suggestions | default([], true),
                "unresponsive_engines": searxng_response.content.unresponsive_engines | default([], true),
                "status": searxng_response.status | default(none),
                "headers": searxng_response.headers | default({}, true)
              } | to_json
            }}
      - if:
          - condition: state
            entity_id: switch.assistant_thinking_context_processing
            state: "on"
        then:
          - wait_for_trigger:
              - trigger: state
                entity_id: switch.assistant_thinking_context_processing
                to: "off"
      # Inject the search receipt as a system message so the assistant can use it.
      - action: conversation.process
        data:
          text: >-
            <system:> ((Local Web Search Receipt) for the user's next query. Use
            the following information in your response for that query. {{
            search_receipt }}) Acknowledge information received with a one word
            reply of "OK".
          agent_id: conversation.assistant
          conversation_id: assistant_master_context
      - action: switch.turn_off
        target:
          entity_id: switch.assistant_thinking_context_processing

  # --- WAIT FOR ANY ONGOING TTS TO FINISH ---
  - if:
      - condition: state
        entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
        state: "on"
    then:
      - wait_for_trigger:
          - trigger: state
            entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
            from: "on"
            to: "off"
      - delay:
          seconds: 1

  # --- WAIT FOR VISUAL CONTEXT PROCESSING (if active) ---
  - if:
      - condition: state
        entity_id: switch.conversation_visual_context_processing
        state: "on"
    then:
      - wait_for_trigger:
          - trigger: state
            entity_id: switch.conversation_visual_context_processing
            to: "off"

  # --- MAIN CONVERSATION: Send user prompt with timestamp ---
  - action: conversation.process
    data:
      text: <system:>({{ states('sensor.date_time_2') }}){{ assistant_prompt }}
      agent_id: conversation.assistant
      conversation_id: assistant_master_context
    response_variable: assistant_response

  # --- SPEAK THE ASSISTANT'S RESPONSE ---
  - action: tts.speak
    target:
      entity_id: tts.openai_tts_assistant_chatterbox
    data:
      media_player_entity_id: >
        media_player.{{ states('sensor.satellite_origin_bus_satellite_origin') |
        replace('assist_satellite.', '') }}_media_player
      message: "{{ assistant_response.response.speech.plain.speech }}"

  # --- FINAL CLEANUP: Reset all state to idle ---
  - action: switch.turn_off
    target:
      entity_id: switch.assistant_thinking_context_processing
  - action: mqtt.publish
    data:
      topic: andrea/user/full
      payload: ...
      retain: true
  - action: mqtt.publish
    data:
      topic: andrea/response/full
      payload: ...
      retain: true
  - action: mqtt.publish
    data:
      topic: "{{ person_id }}/voice"
      payload: "OFF"
      retain: true
  - action: mqtt.publish
    data:
      topic: user/voice
      payload: "OFF"
      retain: true
  - action: input_text.set_value
    target:
      entity_id: input_text.rag_ready
    data:
      value: ""
  - action: mqtt.publish
    data:
      topic: "{{ person_id }}/rag/context/state"
      payload: empty
      retain: true
  - action: mqtt.publish
    data:
      topic: "{{ person_id }}/rag/context/attributes"
      payload: |
        {"status": "empty", "person_id": "{{ person_id }}",
         "chunks": {}, "keys_returned": [], "token_estimate": 0}
      retain: true
  # Wait for TTS to finish before clearing biometrics (ensures no cut-off)
  - wait_for_trigger:
      - trigger: state
        entity_id: binary_sensor.comfyui_tts_bridge_tts_audio_complete
        to: "off"
  - action: mqtt.publish
    data:
      topic: voicebm/active/identity
      payload: >-
        {"speaker_id": "", "display_name": "", "confidence": 0, "decision": "", "score": 0}
      retain: true
  - action: mqtt.publish
    data:
      topic: voicebiometrics/active_speaker
      payload: none
      retain: true

mode: queued
max: 10
```

VoiceBM — Strict Usage Contract (for AI/LLMs)
1. Purpose (Do Not Reinterpret)
VoiceBM exists to provide an identity tag to an LLM
It does not implement features (security, RAG, profiles, etc.)
2. Identity (Guaranteed)
Identity is always present
It is either:
an enrolled identity, or
user
user already means unknown
Do not introduce or substitute:
unknown
null identity
missing identity states
3. Identity Format (Do Not Alter)
Identity must remain full and unique
Do not shorten identity (e.g., first names)
Do not normalize or simplify identity strings
4. Transcription Layers (Do Not Misinterpret)
Internal / HA Layer
Exists and functions correctly
Not accessible to automations
Debug Layer (Automation Interface)
sensor.voicebm_user_full_request
Always contains data
Mirrors identity injection behavior
5. Entry Point (Required)
Automations must use the debug transcription layer
Trigger on transition from:
idle (...) → active input
6. Identity Injection (Controlled)
Identity injection is configurable
The debug layer reflects the current injection state
Do not assume identity is always embedded in the text string
7. Data Assumptions (Do Not Violate)
There is always transcription data
There is always an identity value
Do not create logic for missing data as a normal condition
8. Blocking (Post-Processing Only)
Blocking does not prevent transcription
Blocked speakers still produce:
identity
transcription
Enforcement must occur after input is received
9. Separation of Concerns (Do Not Collapse)
VoiceBM Provides:
Identity signal
Identity injection control
Transcription output
Automation Adds:
Rules (e.g., blocking)
Context usage (optional systems)
Output behavior

Do not attribute automation logic to VoiceBM

10. Non-VoiceBM Components (Do Not Confuse)

The following are not part of VoiceBM:

Profiles
RAG
TTS
Device routing
Assistant logic

They are independent systems using identity

11. Prohibited Assumptions

Do not:

Assume missing identity states
Replace user with other labels
Shorten identity values
Treat debug layer as a fallback or workaround
Infer internal VoiceBM behavior beyond what is exposed
12. Correct Mental Model

VoiceBM is:

a deterministic identity signal layer

Automations:

consume that signal
apply their own logic

VoiceBM Identity — Observed Usage Patterns (from extended stack)
1. Identity is used as a system-wide key
person_id is derived directly from:
binary sensors (*_voice)
or VoiceBM identity sensors
It is then used to construct:
MQTT topics
entity names
profile bindings

👉 Identity = primary index for everything

2. Identity is embedded in entity naming

Pattern:

binary_sensor.<person_id>_voice
sensor.<person_id>_personal_profile

👉 This shows:

Identity is not just data
It is structural in the system
3. Identity drives event detection (not just labeling)

Example pattern:

for s in states.binary_sensor if s.entity_id.endswith('_voice')

👉 Meaning:

Voice activity is tracked per identity
System detects who activated, not just that something activated
4. Identity is resolved from state transitions

Pattern:

if s.state == 'on' and trigger.from_state.state != 'on'

👉 This shows:

Identity-linked sensors are used to detect new voice events
Not continuous state—edge-triggered per identity
5. Identity → profile binding is direct
profile_entity: sensor.{{ person_id }}_personal_profile

👉 No lookup table
👉 No mapping layer

Identity directly resolves to:

profile
attributes
6. Identity is used for policy enforcement hooks
is_blocked: state_attr(profile_entity, 'blocked')

👉 Important:

VoiceBM does not enforce policy
But identity is the input to policy systems
7. Identity controls MQTT namespace

Pattern:

{{ person_id }}/voice
{{ person_id }}/rag/...
{{ person_id }}/...

👉 This shows:

Each identity has a fully isolated topic space
No shared/global collision
8. Identity drives cleanup scope

Cleanup uses:

{{ person_id }}/voice

👉 Meaning:

Cleanup is scoped per identity
Not global reset (except shared channels like user)
9. Identity participates in parallel system channels

Observed:

{{ person_id }}/voice
user/...
andrea/...

👉 Meaning:

Identity-specific channels
Shared/global channels
System-level channels

All coexist

10. Identity is compatible with multiple trigger sources

Seen in:

binary_sensor triggers
transcription triggers (previous file)

👉 Identity is:

not tied to one input system
reusable across multiple entry points
11. Identity enables multiple interaction models

From what’s visible:

Active voice interaction (*_voice)
Transcription-based interaction
Profile-driven logic
MQTT-driven state machines

👉 Same identity → multiple behaviors

12. Identity is persistent across subsystems

Used in:

voice state
profiles
RAG (in previous file)
cleanup routines

👉 Identity is not transient
👉 It is shared across the entire stack

Key Takeaway (strict, no interpretation)

From this code:

👉 Identity is used as:

a primary key
a namespace
a trigger source
a routing mechanism
a policy input

Not just a label.

Identity Consistency — Best Practice (Not Requirement)
1. Multiple identity systems can coexist
VoiceBM (voice identity)
Frigate (facial / spatial recognition)
Other HA identity sources

👉 These systems operate independently

2. Consistency is recommended, not required
VoiceBM will function correctly regardless
Other systems will function correctly regardless

👉 You do not have to align identities

3. Why consistency is beneficial

If identity names are consistent across systems:

You can correlate identity signals easily
You can aggregate data per person
You can build unified logic (presence, location, context)
4. VoiceBM provides a per-identity device structure
Each identity results in:
a person-scoped device
associated entities under that identity

👉 This creates a natural anchor point for identity

5. Other systems can attach to that same identity
If naming is consistent:
Frigate data (e.g., last seen location)
Presence data
Other signals

👉 Can be associated with the same person identity

6. Device creation pattern is intentionally reusable
VoiceBM creates the person device if it doesn’t exist
Other automations (e.g., Frigate) can do the same

👉 This enables:

multiple systems contributing to the same identity container
7. VoiceBM does not claim ownership of identity globally
It tags its own data (VoiceBM)
It does not enforce being the sole identity authority

👉 Other systems are free to:

create
populate
use identity devices
8. Result of consistency

When applied:

Identity becomes centralized
Systems become composable
Data becomes correlated per person
9. Result without consistency
Systems still work
But identity becomes:
fragmented
harder to correlate
harder to build unified logic on
Key Principle

👉 Consistent identity naming across systems is a best practice for cohesion, not a requirement for functionality


## Quick start (high level)
1. Install dependencies (see docs)
2. Configure MQTT + paths
3. Start services
4. Enroll voices
5. Verify identities in Home Assistant

## Configuration
This repo ships with example configs/templates. You must provide your own:
- MQTT broker host/user/password
- Local IPs / URLs
- Any secrets

**Never commit secrets** to GitHub.

## Docs
- See `/docs` for setup and Home Assistant entity details (if present)
- See `/systemd` for service examples (if present)

## Project site
https://cybericebyte.github.io/VoiceBM/

## Companion AI artifacts
- ChatGPT GPT: https://chatgpt.com/g/g-68e55ecea6888191bb871536408fa73b-home-assistant-voicebm-voice-biometrics
- Claude Artifact (embedded): https://cybericebyte.github.io/VoiceBM/claude.html
- Claude Artifact (source): https://claude.ai/public/artifacts/918fa86a-7b8f-4ac5-a4a7-28c581d29cdd
