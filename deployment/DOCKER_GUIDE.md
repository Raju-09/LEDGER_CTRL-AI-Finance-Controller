# Container Build & Optimization

Production Docker builds leverage multi-stage layers:
1. `builder` stage: wheels and requirements compilation
2. `runner` stage: minimal alpine python runtime (<95MB)
