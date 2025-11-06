#pragma once
#include "service_32.h"
#include "model_32.h"
#include <memory>

class Controller32 {
public:
    Controller32();
    void initialize();
    void run();
private:
    std::unique_ptr<Service32> service_;
    std::shared_ptr<Model32> model_;
};
