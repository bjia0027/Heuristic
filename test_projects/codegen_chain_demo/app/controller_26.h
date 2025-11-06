#pragma once
#include "service_26.h"
#include "model_26.h"
#include <memory>

class Controller26 {
public:
    Controller26();
    void initialize();
    void run();
private:
    std::unique_ptr<Service26> service_;
    std::shared_ptr<Model26> model_;
};
