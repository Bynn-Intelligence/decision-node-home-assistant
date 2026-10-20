# DecisionNode for Home Assistant

DecisionNode is a decision engine. This integration lets Home Assistant ask it calibrated
questions about your cameras' pictures, an image or any state, and get typed answers back:
a yes-or-no probability, a choice from options you name, a score on your scale or a
number. Use the answers in automations, as sensors, or on a Frigate detection.

- A **decide** action (`decisionnode.decide`) that asks questions about a camera's picture,
  an image or a state and returns the answers, as an action response and as the event
  `decisionnode_decision`.
- **Standing questions**: a question asked on a schedule about a camera, shown as a binary
  sensor (yes or no) or a sensor (a choice, a score or a number).
- A **Frigate trigger**: a person or car detection asks your questions about that event's
  snapshot.
- **Knowledge**: any of them can apply your own documents, such as house rules or appliance
  manuals, and shows the passages a decision cites.

## Install

Until the integration is listed in HACS, add it as a custom repository:

1. In Home Assistant, open **HACS**, then the three-dot menu, **Custom repositories**.
2. Enter `https://github.com/Bynn-Intelligence/decision-node-home-assistant`, choose the
   type **Integration**, and select **Add**.
3. Find **DecisionNode** in HACS, select **Download**, and restart Home Assistant.
4. Go to **Settings**, **Devices & services**, **Add integration**, and pick **DecisionNode**.
5. Paste an API key from your DecisionNode console. The model defaults to
   `decisionnode-moe`; `decisionnode-flash` is the fast, lower-cost model.

The key is kept in the integration's configuration and is never written to the log. If
DecisionNode refuses it later, Home Assistant asks you for a new one.

## The decide action

Questions are written as the DecisionNode API takes them: an id, then a `type` (`truth`,
`choice`, `score`, `number`, `point` or `box`) and `instructions`.

```yaml
action: decisionnode.decide
data:
  camera_entity_id: camera.front_door
  questions:
    package:
      type: truth
      instructions: Is a package on the doorstep?
    visitor:
      type: choice
      instructions: Who is at the door?
      criteria:
        courier: a delivery driver
        guest: someone visiting
        nobody: no one is there
response_variable: decision
```

The response holds `answers` by question id, exactly as the API sends them, with the
`model` that answered and the `request_id`:

```yaml
answers:
  package: { type: truth, truth: 0.94 }
  visitor: { type: choice, choice: courier, confidence: 0.81, probabilities: { courier: 0.81, guest: 0.12, nobody: 0.07 } }
model: decisionnode-moe-<version>
request_id: req_...
```

Instead of a camera, pass `image_url` (an https URL that DecisionNode fetches) or
`image_path` (a file in a directory listed in `allowlist_external_dirs`). Add `state` to
give the questions text or data beside the picture.

An automation that turns on the porch light when a package is likely there:

```yaml
automation:
  - alias: Light the porch for a package
    triggers:
      - trigger: state
        entity_id: binary_sensor.front_door_motion
        to: "on"
    actions:
      - action: decisionnode.decide
        data:
          camera_entity_id: camera.front_door
          questions:
            package:
              type: truth
              instructions: Is a package on the doorstep?
        response_variable: decision
      - if:
          - condition: template
            value_template: "{{ decision.answers.package.truth > 0.8 }}"
        then:
          - action: light.turn_on
            target:
              entity_id: light.porch
```

Every decision also fires the event `decisionnode_decision`, with `source` (`service`,
`standing` or `frigate`) and the same fields, so other automations can react to it.

## Standing questions

Open the integration's **Configure** dialog and list your standing questions as YAML:

```yaml
- name: Package at the door
  camera: camera.front_door
  question:
    type: truth
    instructions: Is a package on the doorstep?
  interval: 120
  threshold: 0.8
- name: Driveway
  camera: camera.driveway
  question:
    type: choice
    instructions: What is in the driveway?
    criteria:
      empty: nothing is parked
      car: a car
      van: a van or a truck
```

A `truth` question becomes a binary sensor, on when the probability reaches `threshold`
(0.5 when left out), with the probability as the `truth` attribute. A `choice`, `score`
or `number` question becomes a sensor whose state is the choice, the score or the number,
with the confidence and the probabilities as attributes. `interval` is in seconds: 60 by
default and at least 10. Each account sends at most two requests at a time, at least one
second apart, so a busy home cannot flood the API.

## Frigate

The Frigate trigger needs Home Assistant's MQTT integration connected to the broker
Frigate publishes on. In the **Configure** dialog:

```yaml
enabled: true
frigate_url: http://frigate.local:5000
topic: frigate/events
labels: [person, car]
cameras: []        # all cameras; or list the ones to watch
event_type: new    # new, update or end
cooldown: 30       # seconds between two decisions for the same camera
questions:
  courier:
    type: truth
    instructions: Is this person a delivery driver?
  blocking:
    type: truth
    instructions: Is a car blocking the driveway?
```

When Frigate reports an event of one of the labels, the integration reads that event's
snapshot from Frigate and asks the questions about it. The answers arrive as the event
`decisionnode_decision` (with `source: frigate`, `event_id`, `camera` and `label`) and on
the sensor **Last Frigate decision**.

A sample automation:

```yaml
automation:
  - alias: Courier at the door
    triggers:
      - trigger: event
        event_type: decisionnode_decision
        event_data:
          source: frigate
          camera: front_door
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.answers.courier.truth > 0.85 }}"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: A courier is at the front door.
```

## Knowledge

A knowledge base holds your own documents: house rules, appliance manuals, the care notes
for a plant or a pet. Name it on a decision and DecisionNode finds the passages that apply
and decides by them, and the response shows which passages it used.

Create the knowledge base and add documents in the DecisionNode console, or with the `dn`
command line tool. A scope key lets one knowledge base hold several rooms or devices, and a
decision names the one it is about:

```sh
dn collections create "Home" --type text --scope-key room
dn documents add col_3f6c... house-rules.md --pinned
dn documents add col_3f6c... dishwasher-manual.pdf --metadata '{"room": "kitchen"}'
dn documents add col_3f6c... thermostat-manual.pdf --metadata '{"room": "hallway"}'
```

A document without the scope key in its metadata applies to every room. A pinned document is
always given to the decision, so pin a rule that must always apply. Documents are processed
in the background; a decision uses those that are ready.

On the decide action, `knowledge` takes the knowledge base's id as `collection` and, as
needed, `scope`, `top_k` (how many passages, 4 by default), `require` and the other
knowledge options (`query`, `max_tokens`, `pinned`, `min_score`, `match`, `filter`,
`include_text`):

```yaml
action: decisionnode.decide
data:
  state: "Dishwasher display: E24, water left in the bottom"
  questions:
    technician:
      type: truth
      instructions: Does the manual say this needs a technician?
  knowledge:
    collection: col_3f6c1a9e0b2d4c7f8a1e5d9b2c4f6a80
    scope: kitchen
    top_k: 4
    require: true
response_variable: decision
```

The response then carries `evidence.knowledge` exactly as the API sends it. Its one result
lists the `passages` the decision cites, pinned ones first:

```yaml
evidence:
  knowledge:
    status: ok
    results:
      - scope: { key: room, value: kitchen }
        passages:
          - { n: 1, pinned: true, title: House rules, heading: Kitchen, item: itm_..., chunk: 0, byte_start: 0, byte_end: 310, score: null }
          - { n: 2, pinned: false, title: Dishwasher manual, heading: Error codes, item: itm_..., chunk: 7, byte_start: 5120, byte_end: 5604, score: 0.8123 }
```

`item` and `chunk` name the document and the part of it; `byte_start` and `byte_end` are
UTF-8 byte offsets into the document's stored text, which the console and
`dn documents get --text` show. A passage's `text` is included only when you set
`include_text: true`, which needs a full access key.

Standing questions and the Frigate trigger take the same `knowledge` setting in the
**Configure** dialog:

```yaml
- name: Dishwasher needs a technician
  state: "Dishwasher display: E24"
  question:
    type: truth
    instructions: Does the manual say this needs a technician?
  knowledge:
    collection: col_3f6c1a9e0b2d4c7f8a1e5d9b2c4f6a80
    scope: kitchen
```

The entity then shows `knowledge_status` and `knowledge_passages` (each passage's `n`,
`pinned`, `title`, `heading`, `reference`, `item`, `chunk` and `score`) as attributes; the
sensor **Last Frigate decision** does the same for the Frigate trigger.

With `require: true`, a decision that could not read the knowledge base fails instead of
deciding without it: the action raises an error naming the reason, such as
`knowledge_collection_empty` when no document is ready, and a standing question shows as
unavailable until the next check. Without it, the decision runs and `evidence.knowledge`
says why no passage was cited.

## Privacy

To be decided, a picture (a camera's current image, a Frigate snapshot or the image you
name) is sent to the DecisionNode API with your questions. Nothing is sent until a
decide action runs, a standing question is due or a Frigate event matches your labels.
A knowledge base stays in your DecisionNode workspace; a decision sends only its id and
options. The DecisionNode terms and privacy policy cover what happens to a request:
https://decisionnode.com.

## Development

The tests run the real DecisionNode Python SDK against a mocked API:

```sh
python -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

The SDK keeps its own HTTPS connection pool: it accepts only a plain `httpx.AsyncClient`,
since it never follows a redirect, and Home Assistant's shared clients are not one. The
client is made in the executor, so its certificate loading never runs in the event loop,
and closed when the integration unloads.

## License

MIT, Bynn Intelligence, Inc.
