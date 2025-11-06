#pragma once
#include "model_13.h"

class UIComponent13 {
public:
    UIComponent13();
    void render();
    void setModel(Model13* model);
private:
    Model13* model_;
};
