# Error codes

The **Error message** sensor shows what the unit's error code means; the **Error code** sensor shows the code itself, as the FGLair app and the wired remote controller display it. This page lists every code the integration knows.

- Codes below 256 are shown as two characters, for example `0b`. Each has its own meaning.
- Codes from 256 are shown as `NN.x`, for example `62.6`. The part before the dot says what failed; the digit after it is a detail code for the service technician, so every `62.x` reads as "Outdoor unit main board fault".
- A code not in this list shows as **Other error**. The **Error code** sensor still shows the code, so you can look it up in your unit's service manual or give it to your installer.
- **No error** means the unit reports no error.

The meanings are written for this integration. They follow two sources:

- **App:** the error tables in the FGLair Android app (version 3.4.3), which Fujitsu ships for these adapters. Every code below is in it.
- **Guide:** Fujitsu General America, *410A Mini-Split Troubleshooting Guide*, part 6-26-FG2020, revised 5/2019 ([PDF, hosted by a Fujitsu dealer](https://ilovemyfujitsu.com/wp-content/uploads/2021/05/fujitsu2019-Troubleshooting-Guide.pdf)). It covers the residential models' codes and how a technician checks each one.

Where the two disagree, the integration follows the app, since it is what Fujitsu shows for the same adapters; the guide's meaning is noted. Meanings differ between model families, so for a repair always check your own unit's service manual.

| Code | Meaning | State | Source |
| --- | --- | --- | --- |
| `01` | Indoor and outdoor units not communicating | `indoor_outdoor_communication` | Guide, app |
| `02` | Room temperature sensor fault | `room_thermistor` | Guide, app |
| `04` | Indoor coil middle temperature sensor fault | `indoor_coil_middle_thermistor` | Guide, app |
| `06` | Indoor coil outlet temperature sensor fault | `indoor_coil_outlet_thermistor` | App (guide: outdoor heat exchanger temperature sensor) |
| `08` | Indoor unit power supply fault | `indoor_power_supply` | App |
| `09` | Indoor unit drain fault | `drain` | App |
| `0A` | Outdoor air temperature sensor fault | `outdoor_air_thermistor` | Guide, app |
| `0C` | Discharge pipe temperature sensor fault | `discharge_thermistor` | Guide, app |
| `0E` | Outdoor heat sink temperature sensor fault | `heat_sink_thermistor` | App |
| `0F` | Discharge temperature too high | `discharge_temperature` | Guide, app |
| `11` | Indoor unit model data fault | `indoor_model_data` | App |
| `12` | Indoor fan motor fault | `indoor_fan_motor` | App |
| `13` | Indoor and outdoor units not communicating | `indoor_outdoor_communication` | Guide, app |
| `15` | Compressor temperature sensor fault | `compressor_thermistor` | Guide, app |
| `16` | High-pressure switch fault | `high_pressure_switch` | Guide, app |
| `17` | Outdoor unit overcurrent trip | `outdoor_trip` | Guide, app |
| `18` | Outdoor unit current sensor fault | `outdoor_current_sensor` | Guide, app |
| `19` | Outdoor active filter or PFC circuit fault | `active_filter` | Guide, app |
| `1A` | Compressor motor control fault | `compressor_control` | Guide, app |
| `1b` | Outdoor fan motor 1 fault | `outdoor_fan_motor_1` | Guide, app |
| `1C` | Internal controller communication fault | `microcomputer_communication` | App |
| `1d` | 2-way valve temperature sensor fault | `two_way_valve_thermistor` | App |
| `1E` | 3-way valve temperature sensor fault | `three_way_valve_thermistor` | App |
| `1F` | Indoor unit capacity mismatch | `indoor_capacity` | Guide, app |
| `20` | Manual/auto button stuck | `manual_auto_button` | App |
| `21` | Air cleaner supply reversed | `air_cleaner_reverse_voltage` | Guide, app |
| `22` | Air cleaner power fault | `air_cleaner_power` | App |
| `24` | Refrigerant pressure too high | `high_pressure` | Guide, app |
| `25` | PFC heat sink temperature fault | `pfc_heat_sink_temperature` | App (guide: PFC circuit over-voltage) |
| `26` | Display fault | `display` | App |
| `27` | Display fault | `display` | App |
| `28` | Outdoor coil inlet temperature sensor fault | `outdoor_coil_inlet_thermistor` | App |
| `29` | Outdoor coil middle temperature sensor fault | `outdoor_coil_middle_thermistor` | App |
| `2A` | Indoor unit power supply fault | `indoor_power_supply` | App |
| `2b` | Compressor temperature too high | `compressor_temperature` | App |
| `2C` | 4-way valve or expansion valve fault | `four_way_or_expansion_valve` | App |
| `2d` | Outdoor heat sink temperature sensor fault | `heat_sink_thermistor` | App |
| `2E` | Damper or inverter fault | `damper_or_inverter` | App |
| `2F` | Refrigerant pressure too low | `low_pressure` | App |
| `30` | Indoor unit address setting fault | `indoor_address` | App |
| `31` | Primary/secondary unit setting fault | `primary_secondary_setting` | App |
| `32` | Wrong number of connected units | `unit_count` | App |
| `33` | Outdoor active filter or PFC circuit fault | `active_filter` | App |
| `34` | Indoor fan motor 2 fault | `indoor_fan_motor_2` | App |
| `35` | Electrical box temperature sensor fault | `electrical_box_thermistor` | App |
| `36` | Indoor unit current sensor fault | `indoor_current_sensor` | App |
| `11.x` | Indoor and outdoor units not communicating | `indoor_outdoor_communication` | Guide, app |
| `12.x` | Wired remote controller not communicating | `remote_controller_communication` | Guide, app |
| `13.x` | Outdoor units not communicating | `outdoor_units_communication` | App |
| `14.x` | Network communication fault | `network_communication` | App |
| `15.x` | Unit scan fault | `unit_scan` | App (guide: automatic airflow adjustment, or check run not finished, depending on model) |
| `16.x` | Peripheral unit not communicating | `peripheral_communication` | App |
| `17.x` | Electricity cost allocation fault | `electricity_apportionment` | App |
| `18.x` | External input/output communication fault | `external_communication` | Guide, app |
| `21.x` | Indoor unit initial setting fault | `indoor_initial_setting` | App (guide: number of wires and pipes) |
| `22.x` | Indoor unit capacity mismatch | `indoor_capacity` | Guide, app |
| `23.x` | Incompatible unit combination | `unit_combination` | Guide, app |
| `24.x` | Wrong number of connected units | `unit_count` | Guide, app |
| `25.x` | Connection pipe length fault | `pipe_length` | App |
| `26.x` | Indoor unit address setting fault | `indoor_address` | Guide, app |
| `27.x` | Primary/secondary unit setting fault | `primary_secondary_setting` | App |
| `28.x` | Other setting fault | `other_setting` | App |
| `29.x` | Wrong number of units on wired remote controller | `remote_controller_unit_count` | Guide, app |
| `31.x` | Indoor unit power supply fault | `indoor_power_supply` | App |
| `32.x` | Indoor unit main board fault | `indoor_main_pcb` | App (guide: indoor unit model data (EEPROM)) |
| `33.x` | Indoor unit extension board fault | `indoor_extension_pcb` | App (guide: indoor fan motor power draw detection) |
| `34.x` | Power relay fault | `power_relay` | App |
| `35.x` | Manual/auto button stuck | `manual_auto_button` | Guide, app |
| `36.x` | Heater relay fault | `heater_relay` | App |
| `37.x` | Indoor unit transmission board fault | `indoor_transmission_pcb` | App |
| `38.x` | Network converter board fault | `network_converter_pcb` | App |
| `39.x` | Indoor unit power circuit fault | `indoor_power_circuit` | App (guide: indoor fan motor power supply) |
| `3A.x` | Indoor unit remote controller circuit fault | `indoor_remote_controller_circuit` | Guide, app |
| `41.x` | Room temperature sensor fault | `room_thermistor` | Guide, app |
| `42.x` | Indoor coil temperature sensor fault | `indoor_coil_thermistor` | Guide, app |
| `43.x` | Humidity sensor fault | `humidity_sensor` | App |
| `44.x` | Light sensor fault | `light_sensor` | App (guide: human sensor) |
| `45.x` | Gas sensor fault | `gas_sensor` | App |
| `46.x` | Float switch fault | `float_sensor` | App |
| `47.x` | Water temperature sensor fault | `water_temperature_sensor` | App |
| `48.x` | Hot water flow sensor fault | `hot_water_flow_sensor` | App |
| `49.x` | Heater sensor fault | `heater_sensor` | App |
| `4A.x` | Indoor air temperature sensor fault | `indoor_air_thermistor` | App |
| `51.x` | Indoor fan motor fault | `indoor_fan_motor` | Guide, app |
| `52.x` | Indoor expansion valve fault | `indoor_expansion_valve` | App |
| `53.x` | Indoor unit drain fault | `drain` | Guide, app |
| `54.x` | Air cleaning fault | `air_cleaning` | App |
| `55.x` | Filter cleaning fault | `filter_cleaning` | App |
| `56.x` | Water circulation pump fault | `water_pump` | App |
| `57.x` | Damper fault | `damper` | Guide, app |
| `58.x` | Intake grille position fault | `intake_grille` | Guide, app |
| `59.x` | Indoor fan motor 2 fault | `indoor_fan_motor_2` | App |
| `5A.x` | Indoor fan motor 3 fault | `indoor_fan_motor_3` | App |
| `5U.x` | Other indoor unit fault | `indoor_other` | App |
| `61.x` | Outdoor unit power supply fault | `outdoor_power_supply` | App |
| `62.x` | Outdoor unit main board fault | `outdoor_main_pcb` | Guide, app |
| `63.x` | Inverter board fault | `inverter_pcb` | Guide, app |
| `64.x` | Outdoor active filter or PFC circuit fault | `active_filter` | Guide, app |
| `65.x` | Outdoor power module (IPM) fault | `power_module` | Guide, app |
| `66.x` | Converter type fault | `converter` | App |
| `67.x` | Outdoor unit power dropout | `power_interruption` | App |
| `68.x` | Outdoor unit magnetic relay fault | `magnetic_relay` | App |
| `69.x` | Outdoor unit transmission board fault | `outdoor_transmission_pcb` | App |
| `6A.x` | Outdoor unit display board fault | `outdoor_display_pcb` | Guide, app |
| `71.x` | Discharge pipe temperature sensor fault | `discharge_thermistor` | Guide, app |
| `72.x` | Compressor temperature sensor fault | `compressor_thermistor` | Guide, app |
| `73.x` | Outdoor coil temperature sensor fault | `outdoor_coil_thermistor` | Guide, app |
| `74.x` | Outdoor air temperature sensor fault | `outdoor_air_thermistor` | Guide, app |
| `75.x` | Suction gas temperature sensor fault | `suction_thermistor` | Guide, app |
| `76.x` | Service valve temperature sensor fault | `valve_thermistor` | App |
| `77.x` | Outdoor heat sink temperature sensor fault | `heat_sink_thermistor` | Guide, app |
| `78.x` | Expansion valve temperature sensor fault | `expansion_valve_thermistor` | App |
| `81.x` | Receiver liquid level sensor fault | `receiver_level_sensor` | App |
| `82.x` | Subcooling temperature sensor fault | `subcooling_thermistor` | Guide, app |
| `83.x` | Liquid pipe temperature sensor fault | `liquid_pipe_thermistor` | Guide, app |
| `84.x` | Outdoor unit current sensor fault | `outdoor_current_sensor` | Guide, app |
| `85.x` | Fan motor current sensor fault | `fan_current_sensor` | App |
| `86.x` | Pressure sensor fault | `pressure_sensor` | Guide, app |
| `87.x` | Oil sensor fault | `oil_sensor` | App |
| `91.x` | Compressor 1 fault | `compressor_1` | App |
| `92.x` | Compressor 2 fault | `compressor_2` | App |
| `93.x` | Compressor failed to start | `compressor_start` | App |
| `94.x` | Outdoor unit overcurrent trip | `outdoor_trip` | Guide, app |
| `95.x` | Compressor motor control fault | `compressor_control` | Guide, app |
| `96.x` | Compressor open-loop control fault | `open_loop_control` | App |
| `97.x` | Outdoor fan motor 1 fault | `outdoor_fan_motor_1` | Guide, app |
| `98.x` | Outdoor fan motor 2 fault | `outdoor_fan_motor_2` | Guide, app |
| `99.x` | 4-way valve fault | `four_way_valve` | App |
| `9A.x` | Outdoor expansion valve fault | `outdoor_expansion_valve` | App |
| `9U.x` | Other outdoor unit fault | `outdoor_other` | App |
| `A1.x` | Discharge temperature too high | `discharge_temperature` | Guide, app |
| `A2.x` | Discharge temperature 2 too high | `discharge_temperature_2` | App |
| `A3.x` | Compressor temperature too high | `compressor_temperature` | Guide, app |
| `A4.x` | Refrigerant pressure fault | `outdoor_pressure` | App |
| `A5.x` | Refrigerant pressure too low | `low_pressure` | Guide, app |
| `A6.x` | Outdoor coil temperature fault | `outdoor_coil_temperature` | App |
| `A7.x` | Suction temperature fault | `suction_temperature` | App |
| `A8.x` | Poor refrigerant flow | `refrigerant_circulation` | App |
| `A9.x` | Current overload | `current_overload` | App |
| `AA.x` | Outdoor unit special operation fault | `outdoor_special_operation` | App |
| `AC.x` | Ambient temperature fault | `ambient_temperature` | App |
| `AF.x` | Outside operating range | `out_of_range` | App |
| `AJ.x` | Freeze protection active | `freeze_protection` | App |
| `C1.x` | Peripheral unit main board fault | `peripheral_main_pcb` | App |
| `C2.x` | Peripheral unit transmission board fault | `peripheral_transmission_pcb` | App |
| `C3.x` | Peripheral unit board 1 fault | `peripheral_pcb_1` | App |
| `C4.x` | Board 2 fault | `pcb_2` | App |
| `C5.x` | Board 3 fault | `pcb_3` | App |
| `C6.x` | Board 4 fault | `pcb_4` | App |
| `C7.x` | Board 5 fault | `pcb_5` | App |
| `C8.x` | Peripheral unit input device fault | `peripheral_input` | App |
| `C9.x` | Display fault | `display` | App |
| `CA.x` | Memory (EEPROM) fault | `memory` | App |
| `CC.x` | Peripheral unit sensor fault | `peripheral_sensor` | App |
| `CF.x` | Peripheral unit USB connector fault | `peripheral_connector` | App |
| `CJ.x` | Other component fault | `other_part` | App |
| `F1.x` | Service tool software fault | `service_tool_software` | App |
| `F2.x` | Service tool adapter fault | `service_tool_adapter` | App |
| `F3.x` | Service tool interface fault | `service_tool_interface` | App |
| `F4.x` | Service tool environment fault | `service_tool_environment` | App |
| `J1.x` | Refrigerant branch (RB) unit fault | `rb_unit` | App |
| `J2.x` | Branch box fault | `branch_box` | Guide, app |
| `J3.x` | Heat recovery ventilation unit fault | `ventilation_unit` | App |
| `J4.x` | Hot water unit fault | `hot_water_unit` | App |
| `J5.x` | Zone controller fault | `zone_control` | App |
| `J6.x` | DX kit fault | `dx_kit` | App |
| `P1.x` | Accessory fan motor fault | `accessory_fan_motor` | App |
| `P2.x` | Gas sensor fault | `gas_sensor` | App |
| `P3.x` | Dust sensor fault | `dust_sensor` | App |
| `P4.x` | Humidity sensor fault | `humidity_sensor` | App |
| `P5.x` | Temperature sensor fault | `temperature_sensor` | App |
| `P6.x` | Accessory EP fault | `accessory_ep` | App |
| `P7.x` | Deodorizing filter fault | `deodorizing_filter` | App |
| `P8.x` | Accessory main board fault | `accessory_main_pcb` | App |
| `P9.x` | Ion generator fault | `ion_generator` | App |
