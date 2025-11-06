#pragma once
#include <functional>
#include <vector>

class Service8 {
public:
    Service8();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
