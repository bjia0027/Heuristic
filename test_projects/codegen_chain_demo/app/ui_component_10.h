#pragma once
#include "model_10.h"

class UIComponent10 {
public:
    UIComponent10();
    void render();
    void setModel(Model10* model);
private:
    Model10* model_;
};
