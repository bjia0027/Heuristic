#pragma once
#include "model_17.h"

class UIComponent17 {
public:
    UIComponent17();
    void render();
    void setModel(Model17* model);
private:
    Model17* model_;
};
