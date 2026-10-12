# Samsung VR Controller

Use a Samsung Gear VR Controller as a general-purpose input device for controlling the operating system.

## Background

I own a Samsung Gear VR Controller (originally sold as an accessory for the Gear VR headset). It is a small handheld Bluetooth Low Energy device with a rich set of inputs, and I would like to reuse it to control my system (e.g. mouse pointer, scrolling, media keys, shortcuts) instead of letting it sit unused.

## Hardware

Inputs available on the controller:

- **Touchpad**: circular, reports finger position and is also clickable
- **Buttons**: trigger, home, back, volume up and volume down
- **Motion sensors**: accelerometer, plus a gyroscope and magnetometer (to be verified on my unit)
- **Connectivity**: Bluetooth Low Energy

## Goal

Turn the controller's inputs into system input events, for example:

- touchpad → mouse movement / scrolling
- touchpad click and trigger → mouse buttons
- other buttons → keyboard shortcuts or media keys
- motion sensors → pointer control or gestures

## Status

Early idea stage. No code yet.
